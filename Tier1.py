import threading
from block_storage_simulator.simulator import BlockStorageSimulator
from block_storage_simulator.gui import SimulatorApp

class Product:
    """Represents a bulk item type in the warehouse."""
    def __init__(self, name, sku):
        self.name = name
        self.sku = sku
        self.quantity = 0

    def add_stock(self, amount):
        if amount > 0:
            self.quantity += amount
            return True
        return False

    def remove_stock(self, amount):
        if 0 < amount <= self.quantity:
            self.quantity -= amount
            return True
        return False

class WarehouseManager:
    """Handles the business logic and Simulator hardware."""
    def __init__(self):
        self.inventory = {}  # SKU: Product object
        # Initialize Hardware
        self.sim = BlockStorageSimulator()
        self.app = SimulatorApp(self.sim)

    def intake(self, sku, name, amount):
        if sku not in self.inventory:
            self.inventory[sku] = Product(name, sku)
        
        # Hardware Action: Add block to simulator for each unit
        for _ in range(amount):
            self.sim.add_block_to_home_pallet()
            
        return self.inventory[sku].add_stock(amount)

    def dispatch(self, sku, amount):
        if sku in self.inventory:
            # Hardware Action: Remove block from simulator for each unit
            # Only remove if logic says we have enough stock
            if amount <= self.inventory[sku].quantity:
                for _ in range(amount):
                    self.sim.remove_block_from_home_pallet()
                return self.inventory[sku].remove_stock(amount)
        return False

    def get_all_items(self):
        return self.inventory.values()

class WarehouseUI:
    """Provides a console-based interface for the operator."""
    def __init__(self, manager):
        self.manager = manager

    def display_stock(self):
        print("\n" + "="*45)
        print(f"{'SKU':<10} | {'Product Name':<20} | {'Stock'}")
        print("-" * 45)
        items = self.manager.get_all_items()
        if not items:
            print(f"{'WAREHOUSE EMPTY':^45}")
        for item in items:
            print(f"{item.sku:<10} | {item.name:<20} | {item.quantity}")
        print("="*45)

    def run_menu(self):
        """The command loop for the terminal."""
        while True:
            self.display_stock()
            print("\nOptions: [1] Incoming  [2] Outgoing  [3] Exit")
            choice = input("Select operation: ")

            if choice == '1':
                sku = input("Enter SKU: ")
                name = input("Enter Product Name: ")
                try:
                    qty = int(input("Quantity to add: "))
                    if self.manager.intake(sku, name, qty):
                        print(f">> SUCCESS: {qty} units received.")
                except ValueError:
                    print(">> ERROR: Quantity must be a number.")

            elif choice == '2':
                sku = input("Enter SKU: ")
                try:
                    qty = int(input("Quantity to remove: "))
                    if self.manager.dispatch(sku, qty):
                        print(f">> SUCCESS: {qty} units dispatched.")
                    else:
                        print(">> ERROR: Insufficient stock or SKU not found.")
                except ValueError:
                    print(">> ERROR: Quantity must be a number.")

            elif choice == '3':
                print("Closing system...")
                self.manager.app.root.destroy() # Close the GUI window
                break

if __name__ == "__main__":
    # 1. Setup the Brain
    manager = WarehouseManager()
    
    # 2. Setup the Voice (UI)
    ui = WarehouseUI(manager)
    
    # 3. Start the UI in a background thread
    threading.Thread(target=ui.run_menu, daemon=True).start()
    
    # 4. Start the Hardware GUI (This keeps the main thread alive)
    manager.app.run()



