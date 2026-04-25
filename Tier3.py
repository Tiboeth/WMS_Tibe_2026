import sys, os, time, threading

# --- TIRE 3 (Indivigual tracking) ---
# --- 1. SIMULATOR IMPORT ---
sys.path.append(os.path.abspath("../block_storage_sim/src"))
try:
    from block_storage_simulator.simulator import BlockStorageSimulator
    from block_storage_simulator.gui import SimulatorApp
    from block_storage_simulator.constants import ConveyorState
    from block_storage_simulator.models import TransferCommand
    HAS_SIMULATOR = True
except ImportError:
    HAS_SIMULATOR = False

class Block:
    """Represents a physical unit with a unique global ID."""
    def __init__(self, serial_number, batch_id):
        self.serial_number = serial_number
        self.batch_id = batch_id
        self.entry_time = time.strftime("%H:%M:%S")
        self.status = "In Storage"

class Batch:
    """Represents an order. Can be appended to over time."""
    def __init__(self, batch_id):
        self.batch_id = batch_id
        self.blocks = []  # List of Block objects currently in storage
        self.total_added = 0
        self.timestamp = time.strftime("%H:%M:%S")

    def add_blocks(self, new_blocks):
        self.blocks.extend(new_blocks)
        self.total_added += len(new_blocks)

class WarehouseMap:
    def __init__(self):
        self.columns = [50.0, 130.0, 210.0, 290.0, 370.0]
        self.rows = [50.0, 120.0, 190.0, 260.0]
        self.slots = {(x, y): [] for y in self.rows for x in self.columns}

    def find_available_slot(self, exclude=None):
        for coords in self.slots:
            if exclude and coords == exclude: continue
            if len(self.slots[coords]) < 2: return coords
        return None

    def get_visual_grid(self):
        grid_str = "\n--- STORAGE GRID (0,0 is Top-Right) ---\n"
        for y in self.rows:
            row_str = "  "
            for x in reversed(self.columns):
                stack = self.slots[(x, y)]
                icon = "[ ]" if not stack else f"[{len(stack)}]" 
                row_str += f"{icon} "
            grid_str += row_str + "\n"
        return grid_str

class BackgroundWorker:
    def __init__(self, simulator, lock):
        self.sim = simulator
        self.lock = lock

    def _sync_move(self, state):
        if HAS_SIMULATOR:
            with self.lock: self.sim.state.conveyor_state = state
            time.sleep(1.5)

    def run_incoming(self, block_list, wms_map):
        self._sync_move(ConveyorState.WAITING_AT_HOME)
        for _ in block_list:
            if HAS_SIMULATOR:
                with self.lock: self.sim.add_block_to_home_pallet()
            time.sleep(0.5)
        self._sync_move(ConveyorState.IMAGING)
        self._sync_move(ConveyorState.WAITING_IN_SLOT)
        for block in reversed(block_list): 
            target = wms_map.find_available_slot()
            if target:
                cmd = TransferCommand(src_x=160.0, src_y=410.0, dst_x=target[0], dst_y=target[1])
                if HAS_SIMULATOR:
                    with self.lock: self.sim.transfer_item(cmd)
                wms_map.slots[target].append(block)
                time.sleep(1.0)
        self._sync_move(ConveyorState.WAITING_AT_HOME)

    def run_reshuffle(self, coords, wms_map):
        moving_block = wms_map.slots[coords].pop()
        new_target = wms_map.find_available_slot(exclude=coords)
        print(f"\n!!! [RESHUFFLE] Moving Block #{moving_block.serial_number} from {coords} to {new_target} !!!")
        self._sync_move(ConveyorState.WAITING_IN_SLOT)
        cmd1 = TransferCommand(src_x=coords[0], src_y=coords[1], dst_x=160.0, dst_y=410.0)
        if HAS_SIMULATOR: 
            with self.lock: 
                self.sim.transfer_item(cmd1)
        time.sleep(1.0)
        cmd2 = TransferCommand(src_x=160.0, src_y=410.0, dst_x=new_target[0], dst_y=new_target[1])
        if HAS_SIMULATOR: 
            with self.lock: 
                self.sim.transfer_item(cmd2)
        wms_map.slots[new_target].append(moving_block)
        time.sleep(1.0)

    def run_pick(self, coords, wms_map):
        target_block = wms_map.slots[coords].pop()
        cmd = TransferCommand(src_x=coords[0], src_y=coords[1], dst_x=160.0, dst_y=410.0)
        if HAS_SIMULATOR: 
            with self.lock: 
                self.sim.transfer_item(cmd)
        time.sleep(1.0)
        return target_block

class WarehouseManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.batches = {}
        self.all_blocks = {} # SerialNumber: BlockObject
        self.all_blocks_history = [] # <--- NEW: Master list for Full Report
        self.total_blocks_created = 0
        self.wms_map = WarehouseMap()
        self.sim = BlockStorageSimulator() if HAS_SIMULATOR else None
        self.worker = BackgroundWorker(self.sim, self.lock)
        self.app = SimulatorApp(self.sim) if HAS_SIMULATOR else None

    def intake(self, qty, batch_id=None):
        if batch_id is None or batch_id not in self.batches:
            batch_id = len(self.batches) + 1
            self.batches[batch_id] = Batch(batch_id)
        
        target_batch = self.batches[batch_id]
        new_blocks = []
        for _ in range(qty):
            self.total_blocks_created += 1
            b = Block(self.total_blocks_created, batch_id)
            new_blocks.append(b)
            self.all_blocks_history.append(b)
            
        target_batch.add_blocks(new_blocks)
        for i in range(0, len(new_blocks), 2):
            self.worker.run_incoming(new_blocks[i:i+2], self.wms_map)

    def perform_hardware_dispatch(self, target_block):
        """Locates block, reshuffles if needed, and removes from simulator."""
        target_coords = None
        for coords, stack in self.wms_map.slots.items():
            if target_block in stack:
                target_coords = coords
                break
        
        if target_coords:
            self.worker._sync_move(ConveyorState.WAITING_IN_SLOT)
            stack = self.wms_map.slots[target_coords]
            # Reshuffle if buried (index 0 but stack size 2)
            if stack.index(target_block) == 0 and len(stack) == 2:
                self.worker.run_reshuffle(target_coords, self.wms_map)
            
            self.worker.run_pick(target_coords, self.wms_map)
            # Remove from Logic
            target_block.status = "Dispatched"
            # Remove from Batch list
            batch = self.batches[target_block.batch_id]
            batch.blocks.remove(target_block)
            
            self.worker._sync_move(ConveyorState.WAITING_AT_HOME)
            if HAS_SIMULATOR:
                with self.lock: self.sim.remove_block_from_home_pallet()
            return True
        return False

    def dispatch_random(self, qty):
        """FIFO Dispatch: Finds oldest available blocks using the history list."""
        removed = 0
        # Filter history for blocks still in storage, sorted by ID (FIFO)
        available_blocks = [b for b in self.all_blocks_history if b.status == "In Storage"]
        
        for block in available_blocks:
            if removed >= qty: break
            if self.perform_hardware_dispatch(block):
                removed += 1

    def dispatch_specific(self, sn):
        """Targeted Dispatch: Search the history list for the ID."""
        # NEW: Find the block in the history list by its serial number
        block = next((b for b in self.all_blocks_history if b.serial_number == sn), None)
        
        if not block:
            return f"Error: Block #{sn} does not exist in history."
            
        if block.status == "Dispatched":
            return f"Error: Block #{sn} is already gone."
        
        if self.perform_hardware_dispatch(block):
            return f"Success: Block #{sn} dispatched."
            
        return f"Error: Could not locate block #{sn} in the grid."

class WMS_Interface:
    def __init__(self, manager):
        self.manager = manager

    def run(self):
        while True:
            print(self.manager.wms_map.get_visual_grid())
            print("1: Incoming | 2: Dispatch | 3: Full Report | 4: Exit")
            choice = input("Command > ")
            if choice == "1":
                q = int(input("Qty: "))
                m = input("(N)ew or (E)xisting batch? ").upper()
                t_id = int(input("Batch ID: ")) if m == "E" else None
                self.manager.intake(q, t_id)
            elif choice == "2":
                mode = input("Dispatch (S)pecific ID or (R)andom FIFO? ").upper()
                if mode == "S":
                    sn = int(input("Enter Block ID: #"))
                    print(self.manager.dispatch_specific(sn))
                else:
                    q = int(input("Quantity: "))
                    self.manager.dispatch_random(qty=q)
            elif choice == "3":
                self.display_full_report() 

            elif choice == "4":
                if HAS_SIMULATOR: self.manager.app.root.destroy()
                break
    def display_full_report(self):
        print("\n" + "!"*85)
        print(f"{'BLOCK ID':<10} | {'BATCH':<8} | {'ADDED':<10} | {'DISPATCHED':<12} | {'STATUS'}")
        print("-" * 85)
        
        total_remaining = 0
        for block in self.manager.all_blocks_history:
            # Determine status and exit time
            is_in_stock = any(block in stack for stack in self.manager.wms_map.slots.values())
            
            if is_in_stock:
                status = "IN STOCK"
                exit_t = "---"
                total_remaining += 1
            else:
                status = "DISPATCHED"
                # Use the block's own timestamp if you added it during dispatch
                exit_t = getattr(block, 'exit_time', "N/A") 
            
            print(f"#{block.serial_number:<9} | {block.batch_id:<8} | {block.entry_time:<10} | {exit_t:<12} | {status}")
            
        print("-" * 85)
        print(f"{'TOTAL QUANTITY REMAINING IN WAREHOUSE:':<73} {total_remaining}")
        print("!"*85 + "\n")

if __name__ == "__main__":
    mngr = WarehouseManager()
    ui = WMS_Interface(mngr)
    threading.Thread(target=ui.run, daemon=True).start()
    if HAS_SIMULATOR: mngr.app.run()
