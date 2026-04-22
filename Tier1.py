import time
import threading

# --- 1. HARDWARE AUTO-DETECTION ---
# Attempts to load simulation libraries. If they fail, 'Mock Mode' is enabled.
try:
    from block_storage_simulator.simulator import BlockStorageSimulator
    from block_storage_simulator.gui import SimulatorApp
    from block_storage_simulator.constants import ConveyorState
    from block_storage_simulator.models import TransferCommand
    HAS_SIMULATOR = True
except ImportError:
    HAS_SIMULATOR = False
    # Dummy classes to prevent logic crashes when libraries are missing
    class ConveyorState:
        WAITING_AT_HOME = "HOME"
        IMAGING = "SCANNING"
        WAITING_IN_SLOT = "STORAGE"

class Batch:
    """Represents a unique shipment. Individual blocks will 'belong' to these IDs."""
    def __init__(self, batch_id, qty):
        self.batch_id = batch_id
        self.initial_qty = qty
        self.current_qty = qty
        self.timestamp = time.strftime("%H:%M:%S")

class WarehouseMap:
    """
    TIER 2 DATA STRUCTURE: 
    Slots are now LISTS [] instead of integers.
    The order in the list represents physical stacking (Index 0 = Bottom, Index 1 = Top).
    """
    def __init__(self):
        self.columns = [50.0, 130.0, 210.0, 290.0, 370.0]
        self.rows = [50.0, 120.0, 190.0, 260.0]
        self.slots = {(x, y): [] for y in self.rows for x in self.columns}

    def find_available_slot(self, exclude_coords=None):
        """Finds a slot with capacity < 2. Used for both intake and reshuffling."""
        for coords, items in self.slots.items():
            if coords != exclude_coords and len(items) < 2:
                return coords
        return None

    def find_batch_location(self, batch_id):
        """
        Locates a specific Batch ID within the grid.
        Returns: (coordinates, depth) where depth 0 is bottom and 1 is top.
        """
        for coords, items in self.slots.items():
            if batch_id in items:
                return coords, items.index(batch_id) 
        return None, None

    def get_visual_grid(self):
        """Dynamic header based on whether the simulation hardware is connected."""
        header = "--- STORAGE GRID (0,0 is Top-Right) ---" if HAS_SIMULATOR else "--- STORAGE GRID (Logic View) ---"
        grid_str = f"\n{header}\n"
        for y in self.rows:
            row_str = "  "
            for x in reversed(self.columns):
                qty = len(self.slots[(x, y)])
                icon = "[ ]" if qty == 0 else "[/]" if qty == 1 else "[X]"
                row_str += f"{icon}  "
            grid_str += row_str + "\n"
        return grid_str

class BackgroundWorker:
    """Executes physical commands. Handles the hand-off between Logic and Hardware."""
    def __init__(self, simulator, lock):
        self.sim = simulator
        self.lock = lock

    def _sync_move(self, state):
        """Standardizes movement timing between GUI and logic."""
        if HAS_SIMULATOR:
            with self.lock: self.sim.state.conveyor_state = state
            time.sleep(1.2)
        else: print(f"  [Mock] Conveyor to: {state}")

    def run_incoming(self, qty, wms_map, batch_id):
        """Executes intake trips. Limits each trip to 2 blocks (max pallet capacity)."""
        self._sync_move(ConveyorState.WAITING_AT_HOME)
        actual_loaded = 0
        for _ in range(qty): 
            if HAS_SIMULATOR:
                with self.lock:
                    if self.sim.add_block_to_home_pallet(): actual_loaded += 1
            else: actual_loaded += 1
            time.sleep(0.1 if not HAS_SIMULATOR else 0.5)

        self._sync_move(ConveyorState.IMAGING)
        self._sync_move(ConveyorState.WAITING_IN_SLOT)
        
        # Physical transfer from pallet to storage slots
        for _ in range(actual_loaded):
            target = wms_map.find_available_slot()
            if target:
                if HAS_SIMULATOR:
                    tx, ty = target
                    cmd = TransferCommand(src_x=160.0, src_y=410.0, dst_x=tx, dst_y=ty)
                    with self.lock:
                        if self.sim.transfer_item(cmd): 
                            wms_map.slots[target].append(batch_id) # Record ID in slot
                else: wms_map.slots[target].append(batch_id)
                time.sleep(0.1 if not HAS_SIMULATOR else 0.8)
        
        self._sync_move(ConveyorState.WAITING_AT_HOME)

    def run_outgoing_at_coords(self, wms_map, target_coords):
        """
        TIER 2 CORE: Retrieves a SPECIFIC block from a specific coordinate.
        Returns the ID of the block actually removed from the stack.
        """
        if HAS_SIMULATOR:
            tx, ty = target_coords
            cmd = TransferCommand(src_x=tx, src_y=ty, dst_x=160.0, dst_y=410.0)
            with self.lock:
                if self.sim.transfer_item(cmd):
                    removed_id = wms_map.slots[target_coords].pop() # LIFO pop
                    self._sync_move(ConveyorState.WAITING_AT_HOME)
                    with self.lock: self.sim.remove_block_from_home_pallet()
                    return removed_id
        else:
            removed_id = wms_map.slots[target_coords].pop()
            print(f"  [Mock] Block {removed_id} removed from {target_coords}")
            return removed_id
        return None

class WarehouseManager:
    """The central brain. Decides WHAT needs to move and WHERE."""
    def __init__(self):
        self.lock = threading.Lock()
        self.batches = []
        self.wms_map = WarehouseMap()
        self.is_running = True
        self.sim = BlockStorageSimulator() if HAS_SIMULATOR else None
        self.app = SimulatorApp(self.sim) if HAS_SIMULATOR else None
        self.worker = BackgroundWorker(self.sim, self.lock)
        print(f">>> System Initialized: {'SIMULATION' if HAS_SIMULATOR else 'LOGIC'} MODE")

    def intake(self, qty):
        """Assigns blocks to a new Batch ID and updates the map."""
        new_batch = Batch(len(self.batches) + 1, qty)
        self.batches.append(new_batch)
        remaining = qty
        while remaining > 0:
            load = min(remaining, 2)
            print(f"\n[Worker] Processing items for Batch {new_batch.batch_id}...")
            self.worker.run_incoming(load, self.wms_map, new_batch.batch_id)
            remaining -= load
        print(f">>> SUCCESS: Batch {new_batch.batch_id} stored.")

    def dispatch(self, qty):
        """TIER 2 SMART BULK DISPATCH: Now with Partial Fulfillment reporting."""
        
        # 1. Check total stock on hand
        total_available = sum(b.current_qty for b in self.batches)
        if total_available == 0:
            print("\n[ERROR] Dispatch failed: The warehouse is currently empty!")
            return

        # 2. Determine fulfillment status
        requested_qty = qty
        missing_qty = 0
        if requested_qty > total_available:
            missing_qty = requested_qty - total_available
            print(f"\n[Warning] Partial Fulfillment: Only {total_available} of {requested_qty} units available.")
            qty = total_available # Limit dispatch to actual stock

        # 3. Determine the "Shopping List" based on FIFO
        target_ids_needed = []
        temp_batches = [Batch(b.batch_id, b.current_qty) for b in self.batches]
        
        rem = qty
        for tb in temp_batches:
            if rem <= 0: break
            take = min(tb.current_qty, rem)
            for _ in range(take):
                target_ids_needed.append(tb.batch_id)
            rem -= take

        actual_removed_log = [] 

        # 4. Retrieval Loop
        while len(target_ids_needed) > 0:
            found_easy_pick = False
            
            for coords, items in self.wms_map.slots.items():
                if len(items) > 0 and items[-1] in target_ids_needed:
                    target_id = items[-1]
                    print(f"\n[Worker] Grabbing Batch {target_id} from {coords}...")
                    
                    self.worker._sync_move(ConveyorState.WAITING_IN_SLOT)
                    rid = self.worker.run_outgoing_at_coords(self.wms_map, coords)
                    
                    if rid:
                        for b in self.batches:
                            if b.batch_id == rid: b.current_qty -= 1
                        
                        target_ids_needed.remove(rid)
                        actual_removed_log.append(rid)
                        found_easy_pick = True
                        break
            
            if found_easy_pick: continue

            # Reshuffle logic
            target_id = target_ids_needed[0]
            coords, depth = self.wms_map.find_batch_location(target_id)
            
            if coords:
                slot_items = self.wms_map.slots[coords]
                top_id = slot_items[-1]
                print(f"\n[Reshuffle] Batch {top_id} is blocking Batch {target_id}. Moving it...")
                
                temp_slot = self.wms_map.find_available_slot(exclude_coords=coords)
                if temp_slot:
                    self.worker._sync_move(ConveyorState.WAITING_IN_SLOT)
                    if HAS_SIMULATOR:
                        tx, ty = coords
                        dx, dy = temp_slot
                        cmd = TransferCommand(src_x=tx, src_y=ty, dst_x=dx, dst_y=dy)
                        with self.lock:
                            if self.sim.transfer_item(cmd):
                                self.wms_map.slots[temp_slot].append(slot_items.pop())
                    else:
                        self.wms_map.slots[temp_slot].append(slot_items.pop())
            else:
                break

        # 5. Final Detailed Reporting
        print(f"\n>>> SUCCESS: {len(actual_removed_log)} blocks removed via FIFO.")
        
        unique_ids = sorted(list(set(actual_removed_log)))
        for b_id in unique_ids:
            count = actual_removed_log.count(b_id)
            print(f"    - Batch {b_id}: {count} {'block' if count == 1 else 'blocks'}")
            
        if missing_qty > 0:
            print(f"    !!! NOTICE: Order was short by {missing_qty} units (Stock Exhausted).")

class WMS_Interface:
    """User input loop and reporting."""
    def __init__(self, manager):
        self.manager = manager

    def display_report(self):
        """Displays batch inventory and visual storage map."""
        print("\n" + "="*50 + "\nBATCH ID | TIME     | STOCK")
        for b in self.manager.batches:
            print(f"{b.batch_id:<8} | {b.timestamp} | {b.current_qty}")
        print(self.manager.wms_map.get_visual_grid() + "="*50)

    def run(self):
        """Primary interaction loop."""
        while self.manager.is_running:
            self.display_report()
            choice = input("1: Incoming | 2: Dispatch | 3: Exit\nSelect: ")
            if choice == "1": self.manager.intake(int(input("Qty: ")))
            elif choice == "2": self.manager.dispatch(int(input("Qty: ")))
            elif choice == "3":
                self.manager.is_running = False
                if HAS_SIMULATOR: self.manager.app.root.destroy()

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


