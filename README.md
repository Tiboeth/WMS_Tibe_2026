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

