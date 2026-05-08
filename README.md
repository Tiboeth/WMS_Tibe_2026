Updeting test
# WMS_Tibe_2026
Warehouse Management System (WMS)
## Project Overview
This Warehouse Management System (WMS) is a Python-based solution designed to model real industrial processes. It tracks the flow of goods from 
Supplier → Warehouse → Customer, ensuring inventory accuracy across three levels of complexity.

## Core Capabilities

Stock Tracking: Monitor exactly what is in stock, what has left, and what remains.
Industrial Logic: Implements FIFO (First-In, First-Out) and individual item serialization.
Lab Ready: Fully compatible with real-time lab devices and the provided simulator.

## Features by Tier

### Tier 1: Bulk Storage 
   -	Tracks simple item counts (quantities).
   -	Basic "Add" and "Remove" operations.
   -	Real-time stock state reporting.
### Tier 2: FIFO Batches 
   -	Tracks items in batches with timestamps/IDs.
   -	Logic: When stock is removed, the system automatically selects the oldest batch first.
   -	Prevents stock stagnation, mimicking perishable or time-sensitive industrial goods.
   
### Tier 3: Individual Tracking 
   -	Unique serialization for every single unit.
   -	Tracks specific Item IDs/Serial Numbers.
   -	Full "Birth-to-Death" history of every item in the facility.

# WMS Tier 3 (Individual Item Tracking) Documentation

## 1. System Overview
The **WMS Tier 3** is a high-precision Warehouse Management System designed to track individual blocks rather than bulk quantities. It utilizes the **ADS Protocol** to bridge a Python-based logic layer with a physical (or simulated) PLC environment.

### Key Capabilities:
*   **Serialized Tracking:** Every block is assigned a unique `#ID` and timestamp.
*   **Automatic Shuffling:** Intelligent "unstacking" logic to retrieve items buried under others.
*   **Flexible Dispatch:** Supports both **FIFO** (First-In, First-Out) and **Direct ID** retrieval.
*   **Dynamic Mapping:** Manages a 5x4 grid with double-stacking capability (Max 39 units).

---

## 2. Technical Specification

### ADS Configuration
The system communicates via the `py_ads_client` library using the following parameters:
*   **PLC IP:** `127.0.0.1`
*   **PLC NetID:** `127.0.0.1.1.1`
*   **PLC Port:** `48898`

### Logic "N+2 / N+1"
To align digital IDs with physical lifter behavior, when two blocks are added simultaneously:
1. The **first** lift is assigned `Next_Seq + 1`.
2. The **second** lift is assigned `Next_Seq`.
This ensures the physical stacking order matches the database sequence.

---

## 3. Operator User Manual

### Getting Started
1. Launch the executable or script.
2. Confirm the message `>>> ADS CONNECTED` appears. 
3. If an error appears, check your PLC simulator connection.

### Handling Inventory

| Command | Action | Description |
| :--- | :--- | :--- |
| **1: Add** | Intake | Enter quantity, load pallet, and press **ENTER**. |
| **2: Remove** | Dispatch | Choose **FIFO** for the oldest stock or **ID** for a specific block. |
| **3: Exit** | Shutdown | Gracefully closes the ADS connection and displays final counts. |

### Understanding System Messages
*   `[STORED] ID: #5`: Confirmation that block #5 is safely in its slot.
*   `[SYSTEM] SHUFFLE`: The lifter is moving a "blocker" item to reach a target item underneath. This is automated; no action is required.
*   `>>> Please unload the pallet`: The pallet has arrived at the home station. Remove the blocks and press **ENTER** to continue.

---

## 4. Maintenance & Safety
*   **Capacity Limit:** The system will block intake if the total count exceeds **39 blocks**.
*   **State Machine:** The system monitors `ConveyorState`. If the system hangs, check if the PLC is stuck in a state other than `101 (Home)`, `120 (Imaging)`, or `140 (Transfer)`.
*   **Data Integrity:** Unique IDs and Timestamps are fixed upon intake and cannot be modified to ensure a reliable audit trail.

---
*Generated for WMS Tier 3 V3.0*
