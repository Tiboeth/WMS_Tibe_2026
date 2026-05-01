# ==============================================================================
# WMS TIER 2 - WAREHOUSE MANAGEMENT SYSTEM (FIFO)
# ==============================================================================
import sys
import time
import uuid
from py_ads_client import ADSClient, ADSSymbol, BOOL, INT, LREAL

# ==============================================================================
# PLC CONFIGURATION
# ==============================================================================
PLC_IP, PLC_NET_ID, PLC_PORT, LOCAL_NET_ID = "127.0.0.1", "127.0.0.1.1.1", 48898, "127.0.0.1.1.2"

SYM_CONVEYOR_STATE = ADSSymbol("StatusVars.ConveyorState", INT)
CMD_SEND_PALLET = ADSSymbol("Remote.send_pallet", BOOL)
CMD_RELEASE_IMAGING = ADSSymbol("Remote.release_from_imaging", BOOL)
CMD_RETURN_PALLET = ADSSymbol("Remote.return_pallet", BOOL)
CMD_TRANSFER_ITEM = ADSSymbol("Remote.transfer_item", BOOL)
VAL_SRC_X, VAL_SRC_Y, VAL_DST_X, VAL_DST_Y = ADSSymbol("Remote.src_x", LREAL), ADSSymbol("Remote.src_y", LREAL), ADSSymbol("Remote.dst_x", LREAL), ADSSymbol("Remote.dst_y", LREAL)

# ==============================================================================
# DATA MODELS
# ==============================================================================
class Block:
    """Unique ID and Timestamp are fixed upon intake and never change."""
    def __init__(self, block_id, timestamp, sequence_num):
        self.id = block_id           # Example: "#1"
        self.timestamp = timestamp   # Shared Batch Time
        self.sequence_num = sequence_num # Numeric value for sorting
class Transaction:
    def __init__(self, order_num, action, qty):
        self.order_num, self.time, self.status = order_num, time.strftime("%H:%M:%S"), f"{action} {qty} block(s)"

class WarehouseMap:
    def __init__(self):
        self.columns, self.rows = [50.0, 130.0, 210.0, 290.0, 370.0], [50.0, 120.0, 190.0, 260.0]
        self.slots = {(x, y): [] for y in self.rows for x in self.columns}

    def get_total_count(self):
        return sum(len(s) for s in self.slots.values())

# ==============================================================================
# SYSTEM MANAGER
# ==============================================================================
class WarehouseManager:
    def __init__(self):
        self.history, self.wms_map = [], WarehouseMap()
        self.client = ADSClient(local_ams_net_id=LOCAL_NET_ID)
        self.MAX_CAPACITY = 39 
        self.next_seq = 1
        try:
            self.client.open(target_ip=PLC_IP, target_ams_net_id=PLC_NET_ID, target_ams_port=PLC_PORT)
        except: sys.exit(1)

    def _wait_state(self, target, label):
        while True:
            try:
                if self.client.read_symbol(SYM_CONVEYOR_STATE) == target: break
            except: pass
            time.sleep(0.3)

    def _move_lifter(self, sx, sy, dx, dy):
        self.client.write_symbol(VAL_SRC_X, sx); self.client.write_symbol(VAL_SRC_Y, sy)
        self.client.write_symbol(VAL_DST_X, dx); self.client.write_symbol(VAL_DST_Y, dy)
        self.client.write_symbol(CMD_TRANSFER_ITEM, True)
        time.sleep(0.2); self.client.write_symbol(CMD_TRANSFER_ITEM, False)
        time.sleep(3.8)

    def _execute_shuffle(self, blocker_coords):
        bx, by = blocker_coords
        # Only shuffle to a completely empty coordinate
        target_slot = next((c for c, s in self.wms_map.slots.items() if len(s) == 0), None)
        
        if target_slot:
            tx, ty = target_slot
            # Identify the block being moved for the log
            blocker_id = self.wms_map.slots[blocker_coords][-1].id
            print(f" [SYSTEM] SHUFFLE: Relocating {blocker_id} from {blocker_coords} to {target_slot}")
            
            self._move_lifter(bx, by, tx, ty)
            
            # Move the block object (preserving all data)
            block_obj = self.wms_map.slots[blocker_coords].pop()
            self.wms_map.slots[target_slot].append(block_obj)


    def intake(self, qty):
        if self.wms_map.get_total_count() + qty > self.MAX_CAPACITY:
            print(" [ABORT] Full!"); return

        remaining = qty
        while remaining > 0:
            trip = 2 if remaining >= 2 else remaining
            self._wait_state(101, "Home")
            batch_time = time.time()
            
            print(f"\n [INTAKE] Batch of {trip} registered at {time.strftime('%H:%M:%S', time.localtime(batch_time))}")
            input(f" >>> Load {trip} blocks and press ENTER...")

            # Path sequence
            self.client.write_symbol(CMD_SEND_PALLET, True)
            self._wait_state(120, "Imaging")
            self.client.write_symbol(CMD_RELEASE_IMAGING, True)
            self._wait_state(140, "Transfer")

            # --- THE "N+2 / N+1" ID LOGIC ---
            if trip == 2:
                # First lift gets #n+1, Second lift gets #n+2
                id_sequence = [self.next_seq + 1, self.next_seq ]
                self.next_seq += 2 
            else:
                id_sequence = [self.next_seq]
                self.next_seq += 1

            for seq_val in id_sequence:
                target = next((c for c, s in self.wms_map.slots.items() if len(s) < 2), None)
                if target:
                    tx, ty = target
                    self._move_lifter(160.0, 410.0, tx, ty)
                    
                    # Create Block: ID matches the sequence number (#1, #2, etc.)
                    new_block = Block(f"#{seq_val}", batch_time, seq_val)
                    self.wms_map.slots[target].append(new_block)
                    
                    print(f" [STORED] ID: #{seq_val} | Batch: {time.strftime('%H:%M:%S', time.localtime(batch_time))}")
                    
            self.client.write_symbol(CMD_RETURN_PALLET, True)
            remaining -= trip

        self.history.append(Transaction(len(self.history)+1, "Added", qty))



    def dispatch(self, qty):
        """Dispatch: Uses Batch Timestamp + Sequence Number to find the oldest block."""
        if self.wms_map.get_total_count() < qty:
            print(" [ABORT] Low Stock."); return

        remaining = qty
        while remaining > 0:
            trip = 2 if remaining >= 2 else remaining
            self.client.write_symbol(CMD_SEND_PALLET, True)
            self._wait_state(120, "Imaging")
            self.client.write_symbol(CMD_RELEASE_IMAGING, True)
            self._wait_state(140, "Transfer")

            for _ in range(trip):
                
                # --- 1. SCAN FOR THE ABSOLUTE OLDEST (Timestamp then SMALLEST ID) ---
                oldest_block, target_coords, target_index = None, None, None

                for coords, stack in self.wms_map.slots.items():
                    for idx, block in enumerate(stack):
                        if oldest_block is None:
                            oldest_block, target_coords, target_index = block, coords, idx
                        else:
                            # Rule 1: Check Batch Timestamp
                            if block.timestamp < oldest_block.timestamp:
                                oldest_block, target_coords, target_index = block, coords, idx
                            
                            # Rule 2: TIE-BREAKER (If timestamps are equal, SMALLEST ID is oldest)
                            elif block.timestamp == oldest_block.timestamp:
                                if block.sequence_num < oldest_block.sequence_num: # < for smaller ID priority
                                    oldest_block, target_coords, target_index = block, coords, idx



                # 2. NECESSARY SHUFFLE CHECK
                if target_index == 0 and len(self.wms_map.slots[target_coords]) == 2:
                    self._execute_shuffle(target_coords)

                # 3. RETRIEVE TARGET
                tx, ty = target_coords
                self._move_lifter(tx, ty, 160.0, 410.0)
                self.wms_map.slots[target_coords].pop()

            self.client.write_symbol(CMD_RETURN_PALLET, True)
            self._wait_state(101, "Home")
            input(f" >>> Batch of {trip} ready. Unload and press ENTER...")
            remaining -= trip
            
        self.history.append(Transaction(len(self.history)+1, "Removed", qty))

# INTERFACE
# ==============================================================================
def main():
    mgr = WarehouseManager()
    while True:
        print("\n" + "="*50 + f"\n ORDER # | TIME | STATUS\n" + "-"*50)
        for t in mgr.history: print(f" {t.order_num:<7} | {t.time:<8} | {t.status}")
        print(f"-"*50 + f"\n TOTAL STOCK: {mgr.wms_map.get_total_count()}\n" + "="*50)
        choice = input("\n 1: Add | 2: Remove | 3: Exit\n Command > ")
        if choice == "1":
            try: mgr.intake(int(input(" Qty: ")))
            except: pass
        elif choice == "2":
            try: mgr.dispatch(int(input(" Qty: ")))
            except: pass
        elif choice == "3":
            mgr.client.close(); break

if __name__ == "__main__": main()
