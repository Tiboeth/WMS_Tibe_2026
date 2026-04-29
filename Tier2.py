import sys
import os
import time
import threading
sys.path.append(os.path.abspath("../block_storage_sim/src"))

# --- TIRE 2 (FIFO) ---
# --- 1. SIMULATOR IMPORT & PATHING ---
# This block allows the code to run even if the simulator library is missing.
try:
    from block_storage_simulator.simulator import BlockStorageSimulator
    from block_storage_simulator.gui import SimulatorApp
    from block_storage_simulator.constants import ConveyorState
    from block_storage_simulator.models import TransferCommand
    HAS_SIMULATOR = True
except ImportError:
    HAS_SIMULATOR = False
    # Define dummy constants to prevent NameErrors in Mock Mode
    class ConveyorState:
        WAITING_AT_HOME = "HOME_POSITION"
        IMAGING = "IMAGING_ZONE"
        WAITING_IN_SLOT = "TRANSFER_ZONE"

class Block:
    """Represents a physical unit with a unique global ID."""
    def __init__(self, serial_number, batch_id):
        self.serial_number = serial_number
        self.batch_id = batch_id

class Batch:
    """Represents an order. Can be appended to over time."""
    def __init__(self, batch_id):
        self.batch_id = batch_id
        self.blocks = []  # List of Block objects currently in storage
        self.total_added = 0
        self.total_dispatched = 0
        self.timestamp = time.strftime("%H:%M:%S")

    def add_blocks(self, new_blocks):
        self.blocks.extend(new_blocks)
        self.total_added += len(new_blocks)

    @property
    def remaining(self):
        return len(self.blocks)

    @property
    def status(self):
        return "IN STOCK" if self.remaining > 0 else "OUT OF STOCK"

class WarehouseMap:
    """Manages slot occupancy and translates logic to physical coordinates."""
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
            with self.lock: self.sim.add_block_to_home_pallet()
            time.sleep(0.5)

        self._sync_move(ConveyorState.IMAGING)
        self._sync_move(ConveyorState.WAITING_IN_SLOT)

        for block in reversed(block_list): # Stack Inversion Rule
            target = wms_map.find_available_slot()
            if target:
                cmd = TransferCommand(src_x=160.0, src_y=410.0, dst_x=target[0], dst_y=target[1])
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
        with self.lock: self.sim.transfer_item(cmd1)
        time.sleep(1.0)
        cmd2 = TransferCommand(src_x=160.0, src_y=410.0, dst_x=new_target[0], dst_y=new_target[1])
        with self.lock: self.sim.transfer_item(cmd2)
        wms_map.slots[new_target].append(moving_block)
        time.sleep(1.0)

    def run_pick(self, coords, wms_map):
        target_block = wms_map.slots[coords].pop()
        cmd = TransferCommand(src_x=coords[0], src_y=coords[1], dst_x=160.0, dst_y=410.0)
        with self.lock: self.sim.transfer_item(cmd)
        time.sleep(1.0)
        return target_block

class WarehouseManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.batches = {} # Dictionary of batch_id: Batch object
        self.total_blocks_created = 0
        self.wms_map = WarehouseMap()
        self.sim = BlockStorageSimulator() if HAS_SIMULATOR else None
        self.worker = BackgroundWorker(self.sim, self.lock)
        self.app = SimulatorApp(self.sim) if HAS_SIMULATOR else None

    def intake(self, qty, batch_id=None):
        # Determine if we use an existing batch or create a new one
        if batch_id is None or batch_id not in self.batches:
            batch_id = len(self.batches) + 1
            self.batches[batch_id] = Batch(batch_id)
        
        target_batch = self.batches[batch_id]
        new_blocks = []
        for _ in range(qty):
            self.total_blocks_created += 1
            new_blocks.append(Block(self.total_blocks_created, batch_id))
        
        target_batch.add_blocks(new_blocks)
        for i in range(0, len(new_blocks), 2):
            self.worker.run_incoming(new_blocks[i:i+2], self.wms_map)

    def dispatch(self, qty):
        removed = 0
        # Strict FIFO: Iterate through batch keys (sorted by creation)
        for b_id in sorted(self.batches.keys()):
            if removed >= qty: break
            batch = self.batches[b_id]
            
            while batch.blocks and removed < qty:
                target_block = batch.blocks[0]
                
                # Locate in physical grid
                for coords, stack in self.wms_map.slots.items():
                    if target_block in stack:
                        self.worker._sync_move(ConveyorState.WAITING_IN_SLOT)
                        if stack.index(target_block) == 0 and len(stack) == 2:
                            self.worker.run_reshuffle(coords, self.wms_map)
                        
                        self.worker.run_pick(coords, self.wms_map)
                        batch.blocks.pop(0)
                        batch.total_dispatched += 1
                        removed += 1
                        self.worker._sync_move(ConveyorState.WAITING_AT_HOME)
                        with self.lock: self.sim.remove_block_from_home_pallet()
                        break

class WMS_Interface:
    def __init__(self, manager):
        self.manager = manager

    def display_simple_report(self):
        print("\n" + "="*40)
        print(f"{'BATCH':<10} | {'TIME':<10} | {'REMAINING'}")
        print("-" * 40)
        for b_id in sorted(self.manager.batches.keys()):
            b = self.manager.batches[b_id]
            print(f"{b.batch_id:<10} | {b.timestamp:<10} | {b.remaining}")
        print(self.manager.wms_map.get_visual_grid())

    def display_full_report(self):
        print("\n" + "!"*70)
        print(f"{'BATCH':<8} | {'ADDED':<10} | {'DISPATCHED':<12} | {'REMAINING':<10} | {'STATUS'}")
        print("-" * 70)
        total_remaining = 0
        for b_id in sorted(self.manager.batches.keys()):
            b = self.manager.batches[b_id]
            total_remaining += b.remaining
            print(f"{b.batch_id:<8} | {b.total_added:<10} | {b.total_dispatched:<12} | {b.remaining:<10} | {b.status}")
        print("-" * 70)
        print(f"{'TOTAL QUANTITY REMAINING IN WAREHOUSE:':<58} {total_remaining}")
        print("!"*70 + "\n")

    def run(self):
        while True:
            self.display_simple_report()
            print("1: Incoming | 2: Dispatch | 3: Full Report | 4: Exit")
            try:
                choice = input("Command > ")
                if choice == "1":
                    q = int(input("Qty: "))
                    mode = input("Add to (N)ew batch or (E)xisting batch? [N/E]: ").upper()
                    target_id = None
                    if mode == "E":
                        target_id = int(input("Enter existing Batch ID: "))
                    self.manager.intake(q, target_id)
                elif choice == "2":
                    self.manager.dispatch(int(input("Qty to dispatch: ")))
                elif choice == "3":
                    self.display_full_report()
                elif choice == "4":
                    if HAS_SIMULATOR: self.manager.app.root.destroy()
                    break
            except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    mngr = WarehouseManager()
    ui = WMS_Interface(mngr)
    threading.Thread(target=ui.run, daemon=True).start()
    if HAS_SIMULATOR: mngr.app.run()
