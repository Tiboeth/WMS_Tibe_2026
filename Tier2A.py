import time
import threading

# --- 1. HARDWARE AUTO-DETECTION ---
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

class Batch:
    """Tracks the identity and remaining quantity of a specific shipment."""
    def __init__(self, batch_id, qty):
        self.batch_id = batch_id
        self.initial_qty = qty
        self.current_qty = qty
        self.timestamp = time.strftime("%H:%M:%S")

class WarehouseMap:
    """Manages slot occupancy and translates logic to physical coordinates."""
    def __init__(self):
        # Physical coordinates defined by the storage rack hardware
        self.columns = [50.0, 130.0, 210.0, 290.0, 370.0]
        self.rows = [50.0, 120.0, 190.0, 260.0]
        self.slots = {(x, y): 0 for y in self.rows for x in self.columns}

    def find_available_slot(self):
        """Returns coordinates of the first slot with space (max 2 items)."""
        for coords, qty in self.slots.items():
            if qty < 2: return coords
        return None

    def find_filled_slot(self):
        """Returns coordinates of the last item added (for retrieval)."""
        for coords, qty in reversed(list(self.slots.items())):
            if qty > 0: return coords
        return None

    def get_visual_grid(self):
        """Creates the text-based ASCII map for the report."""
        # Determine header based on current mode
        if HAS_SIMULATOR:
            header = "--- STORAGE GRID (0,0 is Top-Right) ---"
        else:
            header = "--- STORAGE GRID (Logic View) ---"
            
        grid_str = f"\n{header}\n"
        
        for y in self.rows:
            row_str = "  "
            for x in reversed(self.columns):
                qty = self.slots[(x, y)]
                icon = "[ ]" if qty == 0 else "[/]" if qty == 1 else "[X]"
                row_str += f"{icon}  "
            grid_str += row_str + "\n"
        return grid_str

class BackgroundWorker:
    """Executes physical movement. Handles both Real Hardware and Mock logic."""
    def __init__(self, simulator, lock):
        self.sim = simulator
        self.lock = lock

    def _sync_move(self, state):
        """Updates hardware state and waits for animation."""
        if HAS_SIMULATOR:
            with self.lock:
                self.sim.state.conveyor_state = state
            time.sleep(1.2) # Wait for physical movement
        else:
            print(f"  [Mock] Conveyor state changed to: {state}")

    def run_incoming(self, qty, wms_map):
        """Moves items from Home to Storage slots."""
        self._sync_move(ConveyorState.WAITING_AT_HOME)
        
        # 1. Load Pallet
        actual_loaded = 0
        for _ in range(qty): 
            if HAS_SIMULATOR:
                with self.lock:
                    if self.sim.add_block_to_home_pallet(): actual_loaded += 1
            else:
                actual_loaded += 1
            time.sleep(0.1 if not HAS_SIMULATOR else 0.5)

        # 2. Transport to Storage
        self._sync_move(ConveyorState.IMAGING)
        self._sync_move(ConveyorState.WAITING_IN_SLOT)
        
        # 3. Store in Racks
        stored_successfully = 0
        for _ in range(actual_loaded):
            target = wms_map.find_available_slot()
            if target:
                if HAS_SIMULATOR:
                    tx, ty = target # Unpack coordinates
                    cmd = TransferCommand(src_x=160.0, src_y=410.0, dst_x=tx, dst_y=ty)
                    with self.lock:
                        if self.sim.transfer_item(cmd):
                            wms_map.slots[target] += 1
                            stored_successfully += 1
                else:
                    wms_map.slots[target] += 1
                    stored_successfully += 1
                time.sleep(0.1 if not HAS_SIMULATOR else 0.8)
        
        self._sync_move(ConveyorState.WAITING_AT_HOME)
        return stored_successfully

    def run_outgoing(self, qty, wms_map):
        """Retrieves items from Storage slots back to Home."""
        self._sync_move(ConveyorState.IMAGING)
        self._sync_move(ConveyorState.WAITING_IN_SLOT)
        
        retrieved_successfully = 0
        for _ in range(qty):
            target = wms_map.find_filled_slot()
            if target:
                if HAS_SIMULATOR:
                    tx, ty = target
                    cmd = TransferCommand(src_x=tx, src_y=ty, dst_x=160.0, dst_y=410.0)
                    with self.lock:
                        if self.sim.transfer_item(cmd):
                            wms_map.slots[target] -= 1
                            retrieved_successfully += 1
                else:
                    wms_map.slots[target] -= 1
                    retrieved_successfully += 1
                time.sleep(0.1 if not HAS_SIMULATOR else 0.8)

        self._sync_move(ConveyorState.WAITING_AT_HOME)
        for _ in range(retrieved_successfully): 
            if HAS_SIMULATOR:
                with self.lock: self.sim.remove_block_from_home_pallet()
            time.sleep(0.1 if not HAS_SIMULATOR else 0.5)
            
        return retrieved_successfully

class WarehouseManager:
    """The system controller that maintains inventory state."""
    def __init__(self):
        self.lock = threading.Lock()
        self.batches = []
        self.wms_map = WarehouseMap()
        self.is_running = True 
        
        if HAS_SIMULATOR:
            # Added this line to show status when simulator is active
            print("\n>>> System Initialized: SIMULATION MODE (Simulator Active)")
            self.sim = BlockStorageSimulator()
            self.app = SimulatorApp(self.sim)
        else:
            print("\n>>> System Initialized: LOGIC-ONLY MODE (Simulator Missing)")
            self.sim = None
            self.app = None
            
        self.worker = BackgroundWorker(self.sim, self.lock)


    def intake(self, qty):
        """Logic for adding new stock."""
        new_batch = Batch(len(self.batches) + 1, qty)
        self.batches.append(new_batch)
        
        remaining = qty
        total_stored = 0
        while remaining > 0:
            load = 2 if remaining >= 2 else 1
            current_count = total_stored + load
            print(f"\n[Worker] Processing {current_count} of {qty} blocks . . .")
            
            stored = self.worker.run_incoming(load, self.wms_map)
            total_stored += stored
            remaining -= load
        
        print(f"\n>>> SUCCESS: {total_stored} blocks were added to storage.")
        new_batch.current_qty = total_stored
        new_batch.initial_qty = total_stored

    def dispatch(self, qty):
        """Logic for removing stock."""
        remaining_work = qty
        total_removed = 0
        while remaining_work > 0:
            load = 2 if remaining_work >= 2 else 1
            current_count = total_removed + load
            print(f"\n[Worker] Removing {current_count} of {qty} blocks . . .")
            
            removed = self.worker.run_outgoing(load, self.wms_map)
            total_removed += removed
            remaining_work -= load

        print(f"\n>>> SUCCESS: {total_removed} blocks were removed from storage.")

        # Deduct from batch records (FIFO)
        rem_to_deduct = total_removed
        for batch in self.batches:
            if rem_to_deduct <= 0: break
            if batch.current_qty > 0:
                take = min(batch.current_qty, rem_to_deduct)
                batch.current_qty -= take
                rem_to_deduct -= take

class WMS_Interface:
    """Command Line Interface for user control."""
    def __init__(self, manager):
        self.manager = manager

    def display_report(self):
        print("\n" + "="*50)
        print(f"{'BATCH ID':<10} | {'TIME':<10} | {'STOCK'}")
        print("-" * 50)
        for b in self.manager.batches:
            print(f"{b.batch_id:<10} | {b.timestamp:<10} | {b.current_qty}")
        print(self.manager.wms_map.get_visual_grid())
        print("="*50)

    def run(self):
        while self.manager.is_running:
            self.display_report()
            print("1: Incoming | 2: Dispatch | 3: Exit")
            try:
                choice = input("Select: ")
                if choice == "1":
                    self.manager.intake(int(input("Qty to add: ")))
                elif choice == "2":
                    self.manager.dispatch(int(input("Qty to remove: ")))
                elif choice == "3":
                    self.manager.is_running = False # Signal the main thread to stop
                    if HAS_SIMULATOR:
                        self.manager.app.root.destroy()
                    break
            except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    mngr = WarehouseManager()
    ui = WMS_Interface(mngr)
    
    # Run the CLI in a separate thread
    threading.Thread(target=ui.run, daemon=True).start()
    
    if HAS_SIMULATOR:
        # Start GUI in the main thread (blocks until window is closed)
        mngr.app.run()
    else:
        # If no GUI, keep main thread alive until user selects 'Exit'       
        while mngr.is_running:
            time.sleep(0.5)
    
    print("\n[System] Shutdown complete. Goodbye!")

