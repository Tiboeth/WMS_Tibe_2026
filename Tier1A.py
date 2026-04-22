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
    """Handles the business logic for stock movement."""
    def __init__(self):
        self.inventory = {}  # Stores SKU: Product object

    def intake(self, sku, name, amount):
        if sku not in self.inventory:
            self.inventory[sku] = Product(name, sku)
        return self.inventory[sku].add_stock(amount)

    def dispatch(self, sku, amount):
        if sku in self.inventory:
            return self.inventory[sku].remove_stock(amount)
        return False

    def get_all_items(self):
        return self.inventory.values()

class WarehouseUI:
    """Provides a console-based interface for the operator."""
    def __init__(self, manager):
        self.manager = manager

    def display_stock(self):
        print("\n" + "="*40)
        print(f"{'SKU':<10} | {'Product Name':<18} | {'Stock'}")
        print("-" * 40)
        items = self.manager.get_all_items()
        if not items:
            print("WAREHOUSE EMPTY")
        for item in items:
            print(f"{item.sku:<10} | {item.name:<18} | {item.quantity}")
        print("="*40)

    def run(self):
        while True:
            self.display_stock()
            print("\nOptions: [1] Incoming (Add)  [2] Outgoing (Remove)  [3] Exit")
            choice = input("Select operation: ")

            if choice == '1':
                sku = input("Enter SKU: ")
                name = input("Enter Product Name: ")
                try:
                    qty = int(input("Enter quantity to add: "))
                    self.manager.intake(sku, name, qty)
                    print(f">> SUCCESS: Added {qty} units.")
                except ValueError:
                    print(">> ERROR: Quantity must be a number.")

            elif choice == '2':
                sku = input("Enter SKU: ")
                try:
                    qty = int(input("Enter quantity to remove: "))
                    if self.manager.dispatch(sku, qty):
                        print(f">> SUCCESS: Dispatched {qty} units.")
                    else:
                        print(">> ERROR: Insufficient stock or SKU not found.")
                except ValueError:
                    print(">> ERROR: Quantity must be a number.")

            elif choice == '3':
                print("Closing system...")
                break
            else:
                print("Invalid option.")

if __name__ == "__main__":
    # Start the single-run operation
    wm = WarehouseManager()
    app = WarehouseUI(wm)
    app.run()
