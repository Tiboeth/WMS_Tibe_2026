import sys
import time
from py_ads_client import ADSClient, ADSSymbol, BOOL, INT, LREAL

# --- 1. ADS CONFIG ---
PLC_IP = "127.0.0.1" 
PLC_NET_ID = "127.0.0.1.1.1"
PLC_PORT = 48898
LOCAL_NET_ID = "127.0.0.1.1.2"

# --- 2. SYMBOL DEFINITIONS ---
SYM_CONVEYOR_STATE = ADSSymbol("StatusVars.ConveyorState", INT)
CMD_SEND_PALLET = ADSSymbol("Remote.send_pallet", BOOL)
CMD_RELEASE_IMAGING = ADSSymbol("Remote.release_from_imaging", BOOL)
CMD_RETURN_PALLET = ADSSymbol("Remote.return_pallet", BOOL)

VAL_SRC_X = ADSSymbol("Remote.src_x", LREAL)
VAL_SRC_Y = ADSSymbol("Remote.src_y", LREAL)
VAL_DST_X = ADSSymbol("Remote.dst_x", LREAL)
VAL_DST_Y = ADSSymbol("Remote.dst_y", LREAL)
CMD_TRANSFER_ITEM = ADSSymbol("Remote.transfer_item", BOOL)

# --- 3. WAREHOUSE MAP (Placed above Manager to avoid NameError) ---
class WarehouseMap:
    def __init__(self):
        self.columns = [50.0, 130.0, 210.0, 290.0, 370.0]
        self.rows = [50.0, 120.0, 190.0, 260.0]
        self.slots = {(x, y): 0 for y in self.rows for x in self.columns}

    def find_available_slot(self):
        for coords, qty in self.slots.items():
            if qty < 2: return coords
        return None

    def find_filled_slot(self):
        for coords, qty in reversed(list(self.slots.items())):
            if qty > 0: return coords
        return None

class Transaction:
    def __init__(self, order_num, action, qty):
        self.order_num = order_num
        self.time = time.strftime("%H:%M:%S")
        self.status = f"{action} {qty} block(s)"

class WarehouseManager:
    def __init__(self):
        self.history = []
        self.total_stock = 0
        self.wms_map = WarehouseMap() 
        self.client = ADSClient(local_ams_net_id=LOCAL_NET_ID)
        try:
            self.client.open(target_ip=PLC_IP, target_ams_net_id=PLC_NET_ID, target_ams_port=PLC_PORT)
            print(f">>> ADS CONNECTED to {PLC_IP}")
        except Exception:
            print("\n" + "!"*50 + "\n ERROR: SIMULATOR IS NOT CONNECTED.\n" + "!"*50)
            sys.exit(1)

    def _wait_state(self, target, label):
        print(f" [CONVEYOR] {label}...")
        while True:
            try:
                if self.client.read_symbol(SYM_CONVEYOR_STATE) == target:
                    break
            except: pass
            time.sleep(0.3)

    def intake(self, qty):
        """Processes intake in batches of 2 (Pallet Limit)."""
        remaining = qty
        total_stored = 0
        
        while remaining > 0:
            # Determine how many to take this trip (max 2)
            trip_qty = 2 if remaining >= 2 else remaining
            
            self._wait_state(101, "Moving to Home Station")
            print(f"\n [TRIP] Processing {trip_qty} of {qty} total blocks...")
            print(f" [HANDSHAKE] Please ADD {trip_qty} block(s) to the pallet in the GUI.")
            input(" >>> Press ENTER once blocks are placed...")

            # 1. Transport to Storage
            self.client.write_symbol(CMD_SEND_PALLET, True)
            self._wait_state(120, "At Imaging Station")
            self.client.write_symbol(CMD_RELEASE_IMAGING, True)
            self._wait_state(140, "At Transfer Slot")
            
            # 2. Store blocks one by one
            for _ in range(trip_qty):
                target = self.wms_map.find_available_slot()
                if target:
                    tx, ty = target
                    self.client.write_symbol(VAL_SRC_X, 160.0) 
                    self.client.write_symbol(VAL_SRC_Y, 410.0)
                    self.client.write_symbol(VAL_DST_X, tx)
                    self.client.write_symbol(VAL_DST_Y, ty)
                    
                    self.client.write_symbol(CMD_TRANSFER_ITEM, True)
                    time.sleep(0.2)
                    self.client.write_symbol(CMD_TRANSFER_ITEM, False)
                    time.sleep(3) 
                    
                    self.wms_map.slots[target] += 1
                    self.total_stock += 1
                    total_stored += 1

            # 3. Return for next batch
            self.client.write_symbol(CMD_RETURN_PALLET, True)
            remaining -= trip_qty
            
        self._wait_state(101, "All trips complete. Returning Home")
        self.history.append(Transaction(len(self.history)+1, "Added", total_stored))

    def dispatch(self, qty):
        """Processes removal in batches of 2 (Pallet Limit)."""
        if self.total_stock < qty:
            print(f" [ABORT] Insufficient Stock. Available: {self.total_stock}")
            return

        remaining = qty
        total_removed = 0
        
        while remaining > 0:
            trip_qty = 2 if remaining >= 2 else remaining
            
            # 1. Go get them
            self.client.write_symbol(CMD_SEND_PALLET, True)
            self._wait_state(120, "At Imaging Station")
            self.client.write_symbol(CMD_RELEASE_IMAGING, True)
            self._wait_state(140, "At Transfer Slot")
            
            for _ in range(trip_qty):
                target = self.wms_map.find_filled_slot()
                if target:
                    tx, ty = target
                    self.client.write_symbol(VAL_SRC_X, tx)
                    self.client.write_symbol(VAL_SRC_Y, ty)
                    self.client.write_symbol(VAL_DST_X, 160.0)
                    self.client.write_symbol(VAL_DST_Y, 410.0)

                    self.client.write_symbol(CMD_TRANSFER_ITEM, True)
                    time.sleep(0.2)
                    self.client.write_symbol(CMD_TRANSFER_ITEM, False)
                    time.sleep(3)
                    self.wms_map.slots[target] -= 1
                    self.total_stock -= 1
                    total_removed += 1

            # 2. Bring to Home
            self.client.write_symbol(CMD_RETURN_PALLET, True)
            self._wait_state(101, "Bringing blocks to Home Station")

            print(f"\n [TRIP] Please REMOVE {trip_qty} block(s) from the pallet.")
            input(" >>> Press ENTER once pallet is cleared...")
            remaining -= trip_qty

        self.history.append(Transaction(len(self.history)+1, "Removed", total_removed))


def main():
    mgr = WarehouseManager()
    while True:
        print("\n" + "="*50 + f"\n ORDER # | TIME     | STATUS\n" + "-"*50)
        for t in mgr.history:
            print(f" {t.order_num:<7} | {t.time:<8} | {t.status}")
        print(f"-"*50 + f"\n TOTAL BLOCKS IN STORAGE: {mgr.total_stock}\n" + "="*50)
        
        print("\n 1: Add | 2: Remove | 3: Exit")
        choice = input(" Command > ")
        if choice == "1":
            try:
                q = int(input(" Qty: "))
                mgr.intake(q)
            except ValueError: print("Enter a number.")
        elif choice == "2":
            try:
                q = int(input(" Qty: "))
                mgr.dispatch(q)
            except ValueError: print("Enter a number.")
        elif choice == "3":
            mgr.client.close()
            break

if __name__ == "__main__":
    main()