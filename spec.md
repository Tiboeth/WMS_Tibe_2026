# Technical Documentation: WMS Tier 3 (Individual Item Tracking)

This document outlines the architecture, logic, and operational flow of the WMS Tier 3 system as defined in the source code.

---

## 1. System Overview
The **WMS Tier 3** is a Warehouse Management System designed for high-precision inventory control. Unlike basic systems, Tier 3 tracks **individual items (Blocks)** using unique IDs, sequence numbers, and timestamps. It interfaces with a physical PLC (Programmable Logic Controller) via the **ADS protocol** to synchronize virtual data with physical movements.

## 2. Technical Architecture

### Communication Layer
*   **Protocol:** TwinCAT ADS.
*   **Connection:** Connects to a PLC at `127.0.0.1` (NetID: `127.0.0.1.1.1`) on Port `48898`.
*   **Data Types:** Uses `BOOL` for commands, `INT` for state machine monitoring, and `LREAL` for high-precision coordinate movement (X/Y axis).

### Data Structures
*   **Block Class:** The core unit. Stores a unique ID (e.g., `#1`), a shared batch timestamp, and a sequence number for sorting.
*   **WarehouseMap:** A 5x4 grid (20 slots total) supporting double-stacking (**Max Capacity: 39**). Coordinates are predefined decimal values (e.g., X: 50.0, 130.0... Y: 50.0, 120.0...).

---

## 3. Core Logic & Features

### A. Intelligent Intake (N+2 / N+1 Logic)
When adding two blocks at once, the system uses a specific **"N+2 / N+1" assignment**. This ensures that the second block handled by the physical lifter is assigned the next logical ID, maintaining a strict correlation between the physical stacking order and the digital database.

### B. Shuffle Mechanism (Automatic Housekeeping)
If a user requests an item that is at the **bottom** of a two-block stack (Index 0):
1.  The system identifies the **"Blocker"** (the item on top).
2.  It automatically finds the nearest empty slot.
3.  The `_execute_shuffle` method moves the blocker to the empty slot before retrieving the target item.

### C. Dispatching Modes
*   **FIFO (First-In, First-Out):** Automatically selects the oldest item based on timestamp and sequence number.
*   **Specific ID:** Allows the operator to request a specific block (e.g., `#5`). The system locates the coordinates, handles any necessary shuffles, and dispatches it.

---

## 4. Operational State Machine
The system relies on reading the `SYM_CONVEYOR_STATE` to progress through physical tasks:
*   **State 101:** Home / Ready.
*   **State 120:** Imaging Station (requires manual release pulse).
*   **State 140:** Transfer Slot (Lifter ready to move).

## 5. Reporting
The main interface generates a **Numerically Sorted Inventory Report**. It sorts by `sequence_num` rather than ID string to ensure that `#10` appears after `#2`, providing a clean, human-readable audit trail of all "In Stock" and "Dispatched" items.

---

> [!IMPORTANT]
> This system requires the `py_ads_client` library and an active ADS route to the target PLC to function. If the simulator is not detected, the system will execute a safety shutdown.
