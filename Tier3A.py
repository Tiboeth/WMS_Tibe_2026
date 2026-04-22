import uuid

class Item:
    """Represents a single, unique unit in the warehouse."""
    def __init__(self):
        self.serial_number = str(uuid.uuid4())[:8]  # Unique 8-character ID

class Product:
    """Manages a collection of unique Item objects."""
    def __init__(self, name, sku):
        self.name = name
        self.sku = sku
        self.items = []  # List of individual Item objects

    def add_items(self, count):
        new_items = [Item() for _ in range(count)]
        self.items.extend(new_items)
        return [item.serial_number for item in new_items]

    def remove_items(self, count):
        if count > len(self.items):
            return None
        
        removed = []
        for _ in range(count):
            # Removes the specific item object
            item = self.items.pop(0) 
            removed.append(item.serial_number)
        return removed

class WarehouseManager:
    def __init__(self):
        self.inventory = {}

    def intake(self, sku, name, count):
        if sku not in self.inventory:
            self.inventory[sku] = Product(name, sku)
        return self.inventory[sku].add_items(count)

    def dispatch(self, sku, count):
        if sku in self.inventory:
            return self.inventory[sku].remove_items(count)
        return None

class WarehouseUI:
    def __init__(self, manager):
        self.manager = manager

    def display_stock(self):
        print("\n" + "="*65)
        print(f"{'SKU':<10} | {'Product Name':<15} | {'Qty':<5} | {'Individual Serial Numbers'}")
        print("-" * 65)
        for sku, product in self.manager.inventory.items():
            serials = ", ".join([item.serial_number for item in product.items])
            # Truncate string for display if too long
            display_serials = (serials[:30] + '...') if len(serials) > 30 else serials
            print(f"{sku:<10} | {product.name:<15} | {len(product.items):<5} | {display_serials}")
        if not self.manager.inventory:
            print("WAREHOUSE EMPTY")
        print("="*65)

    def run(self):
        while True:
            self.display_stock()
            print("\nOptions: 1: Intake (New Units)  2: Dispatch (By Qty)  3: Exit")
            choice = input("Action: ")

            if choice == '1':
                sku = input("SKU: ")
                name = input("Name: ")
                qty = int(input("How many units to create?: "))
                serials = self.manager.intake(sku, name, qty)
                print(f">> Created units with IDs: {', '.join(serials)}")

            elif choice == '2':
                sku = input("SKU: ")
                qty = int(input("Quantity to remove: "))
                removed_ids = self.manager.dispatch(sku, qty)
                if removed_ids:
                    print(f">> Dispatched specific IDs: {', '.join(removed_ids)}")
                else:
                    print(">> Error: Stock unavailable.")

            elif choice == '3':
                break

if __name__ == "__main__":
    wm = WarehouseManager()
    app = WarehouseUI(wm)
    app.run()
