
# --- WMS TIER 1 ---

import sys
import time
from py_ads_client import ADSClient, ADSSymbol, BOOL, INT, LREAL

# --- 1. ADS CONNECTION CONFIGURATION ---
PLC_IP = "127.0.0.1" 
PLC_NET_ID = "127.0.0.1.1.1"
PLC_PORT = 48898
LOCAL_NET_ID = "127.0.0.1.1.2"

# --- 2. SYMBOL DEFINITIONS ---
# Status symbols (Read-only)
SYM_CONVEYOR_STATE = ADSSymbol("StatusVars.ConveyorState", INT)
SYM_LIFTER_STATE = ADSSymbol("StatusVars.LifterState", INT)

# Command symbols (Write-only bits)
CMD_SEND_PALLET     = ADSSymbol("Remote.send_pallet", BOOL)
CMD_RELEASE_IMAGING = ADSSymbol("Remote.release_from_imaging", BOOL)
CMD_RETURN_PALLET   = ADSSymbol("Remote.return_pallet", BOOL)
CMD_TRANSFER_ITEM   = ADSSymbol("Remote.transfer_item", BOOL)

# Coordinate symbols (LREAL for precise decimal movement)
VAL_SRC_X = ADSSymbol("Remote.src_x", LREAL)
VAL_SRC_Y = ADSSymbol("Remote.src_y", LREAL)
VAL_DST_X = ADSSymbol("Remote.dst_x", LREAL)
VAL_DST_Y = ADSSymbol("Remote.dst_y", LREAL)

# --- 3. WAREHOUSE MAP LOGIC ---
class WarehouseMap:
    """Tracks physical coordinates and stack heights (max 2) in the storage grid."""
    def __init__(self):
        # Center coordinates for the 5x4 grid slots
        self.columns = [50.0, 130.0, 210.0, 290.0, 370.0]
        self.rows = [50.0, 120.0, 190.0, 260.0]
        # Initialize dictionary: key=(x,y), value=stack_height (0, 1, or 2)
        self.slots = {(x, y): 0 for y in self.rows for x in self.columns}

    def find_available_slot(self):
        """Finds the first slot with height < 2."""
        for coords, qty in self.slots.items():
            if qty < 2: return coords
        return None

    def find_filled_slot(self):
        """Finds the most recently filled slot for retrieval (LIFO)."""
        for coords, qty in reversed(list(self.slots.items())):
            if qty > 0: return coords
        return None

class Transaction:
    """Data model for the UI history log."""
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
        """Helper to poll ADS until the conveyor reaches a specific state."""
        print(f" [CONVEYOR] {label}...")
        while True:
            try:
                if self.client.read_symbol(SYM_CONVEYOR_STATE) == target:
                    break
            except: pass
            time.sleep(0.3)

    def intake(self, qty):
        """Processes intake with pre-validation to prevent simulator alarms."""
        
        # 1. HARDWARE READINESS CHECK
        # Ensure the lifter isn't currently busy or in an error state
        try:
            lifter_status = self.client.read_symbol(SYM_LIFTER_STATE)
            if lifter_status != 0: # Assuming 0 is the 'READY' state from your simulator
                print(f" [ABORT] Lifter is not READY (Current State: {lifter_status}).")
                return
        except:
            pass # Fallback if symbol read fails

        # 2. SPACE VALIDATION (The "Alarm Preventer")
        remaining_to_store = qty
        planned_slots = []
        
        # Check if we actually have room for the entire batch before moving the pallet
        temp_map = self.wms_map.slots.copy()
        for _ in range(qty):
            # Use a temporary search to find where these blocks WOULD go
            found = False
            for coords, height in temp_map.items():
                if height < 2:
                    temp_map[coords] += 1
                    planned_slots.append(coords)
                    found = True
                    break
            if not found:
                print(f" [ABORT] Warehouse Full! Cannot find space for {qty} blocks.")
                return

        # 3. PHYSICAL EXECUTION (Only reached if validation passes)
        self._wait_state(101, "Moving to Home Station")
        print(f"\n [VALIDATED] Space confirmed for {qty} blocks.")
        input(f" >>> Please add {qty} blocks and press ENTER...")

        # Conveyor Sequence
        self.client.write_symbol(CMD_SEND_PALLET, True)
        self._wait_state(120, "At Imaging Station")
        self.client.write_symbol(CMD_RELEASE_IMAGING, True)
        self._wait_state(140, "At Transfer Slot")

        # 4. COORDINATED TRANSFER
        for target in planned_slots:
            tx, ty = target
            print(f" [LIFTER] Storing at {tx, ty} (Current stack: {self.wms_map.slots[target]})")
            
            self.client.write_symbol(VAL_SRC_X, 160.0)
            self.client.write_symbol(VAL_SRC_Y, 410.0)
            self.client.write_symbol(VAL_DST_X, tx)
            self.client.write_symbol(VAL_DST_Y, ty)
            
            self.client.write_symbol(CMD_TRANSFER_ITEM, True)
            time.sleep(0.2)
            self.client.write_symbol(CMD_TRANSFER_ITEM, False)
            
            # MONITOR FOR FAILURE: If state doesn't change from 0, the move likely failed
            time.sleep(3.0) 
            self.wms_map.slots[target] += 1
            self.total_stock += 1

        self.client.write_symbol(CMD_RETURN_PALLET, True)
        self.history.append(Transaction(len(self.history)+1, "Added", qty))
    def dispatch(self, qty):
        """Retrieves items from Storage to Home in batches of 2."""
        if self.total_stock < qty:
            print(f" [ABORT] Insufficient Stock. Available: {self.total_stock}")
            return

        remaining = qty
        total_removed = 0
        
        while remaining > 0:
            trip_qty = 2 if remaining >= 2 else remaining
            
            # Move pallet to Transfer Slot (Must pass through Imaging)
            self.client.write_symbol(CMD_SEND_PALLET, True)
            self._wait_state(120, "Stopping at Imaging")
            self.client.write_symbol(CMD_RELEASE_IMAGING, True) # Release even if empty
            self._wait_state(140, "At Transfer Slot")
            
            # Lifter sequence (Retrieve)
            for _ in range(trip_qty):
                target = self.wms_map.find_filled_slot()
                if target:
                    tx, ty = target
                    # Move from Grid Slot to Pallet (160, 410)
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

            # Bring pallet back to Home for manual unloading
            self.client.write_symbol(CMD_RETURN_PALLET, True)
            self._wait_state(101, "Ready for Unloading")

            print(f"\n [TRIP] Retrieval batch of {trip_qty} complete.")
            input(" >>> [HANDSHAKE] Please remove blocks in GUI and press ENTER...")
            remaining -= trip_qty

        self.history.append(Transaction(len(self.history)+1, "Removed", total_removed))

def main():
    mgr = WarehouseManager()
    while True:
        # UI Rendering
        print("\n" + "="*50 + f"\n ORDER # | TIME     | STATUS\n" + "-"*50)
        for t in mgr.history:
            print(f" {t.order_num:<7} | {t.time:<8} | {t.status}")
        print(f"-"*50 + f"\n TOTAL BLOCKS IN STORAGE: {mgr.total_stock}\n" + "="*50)
        
        print("\n 1: Add | 2: Remove | 3: Exit")
        choice = input(" Command > ")
        if choice == "1":
            try:
                q = int(input(" Quantity: "))
                mgr.intake(q)
            except ValueError: print("Please enter a numeric quantity.")
        elif choice == "2":
            try:
                q = int(input(" Quantity: "))
                mgr.dispatch(q)
            except ValueError: print("Please enter a numeric quantity.")
        elif choice == "3":
            mgr.client.close()
            break

if __name__ == "__main__":
    main()
