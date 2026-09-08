# Chapter 1: Architecture, Design Patterns & Complete Workflow

This document explains the overarching system architecture, design patterns, and the full step-by-step lifecycle of how data moves from a raw Windows text report into an interactive web interface.

---

## 🏗️ 1. High-Level Architecture

The project is structured following the **Layered Architecture** and **Repository Pattern**. This guarantees that:
1. The **Parser** has zero knowledge of the web framework.
2. The **Services (Business Logic)** have zero knowledge of HTML/CSS.
3. The **Flask Web Application** only interacts with high-level services, never touching raw files or performing low-level string parsing directly.

```text
+-------------------------------------------------------------------------------+
|                             PRESENTATION LAYER                                |
|   Flask Routes (app.py)  <--->  Jinja2 Templates (*.html)  <--->  JS / CSS    |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                            BUSINESS LOGIC LAYER                               |
|   HealthService (health_service.py)   <--->   ChangeDetector (change_detector)|
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                            PARSER & ETL LAYER                                 |
|   TxtParser (txt_parser.py)           <--->   DataNormalizer (normalizer.py)  |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                             DATA ACCESS LAYER                                 |
|   InventoryService (inventory_service.py) -> Filesystem Storage (data/)       |
|   [Snapshots JSON, Normalized Records, Global Changes Log, Raw TXT Archive]   |
+-------------------------------------------------------------------------------+
```

---

## 🔄 2. Complete Step-by-Step Data Workflow

Here is exactly what happens from the moment a user uploads a `.txt` health report until it appears on their screen:

### **Step 1: Input Ingestion**
- A user uploads a file through the browser at `/upload`, triggers a folder import from `C:\healthcheck`, or an automated script sends a `POST` request to `/api/upload`.
- Flask receives the file stream, validates that the extension is `.txt`, checks that the file is not empty, and passes the content or file path to `InventoryService.process_report_file()`.

### **Step 2: Section & Key-Value Parsing (`TxtParser`)**
- `TxtParser` reads the text line-by-line.
- It looks for section divider lines (e.g. `==== COMPUTER / OPERATING SYSTEM ====`).
- Instead of relying on rigid, brittle line numbers, it operates as a state machine:
  - It recognizes header lines like `IP Address : 192.168.1.50`.
  - It recognizes item blocks like `RAM STICK #1`, `DISK #1`, `GPU`, `USB Device`.
  - It outputs a structured raw Python dictionary containing extracted strings.

### **Step 3: Data Normalization & Cleaning (`DataNormalizer`)**
- `DataNormalizer` receives the raw dictionary.
- It cleans whitespace and sets sensible defaults (`"N/A"`).
- It extracts numeric values:
  - `"16.0 GB"` $\rightarrow$ `16.0` (float)
  - `"3200 MHz"` $\rightarrow$ `3200` (int)
  - `"56.98 %"` $\rightarrow$ `56.98` (float)
- **Disk Merging**: It matches physical disks (e.g. `DISK #1`) with SMART health entries (e.g. `STORAGE HEALTH`) using Serial Numbers or Model Names, combining size, health status (`Healthy`), operational status (`OK`), and media type (`SSD` or `HDD`).
- **Software Segregation**: It extracts all 270+ installed software items and stores them safely in an `installed_software` list, keeping the primary hardware view lightweight and clean.

### **Step 4: Health Assessment & Recommendations (`HealthService`)**
- `HealthService` inspects the normalized record against enterprise rules:
  1. **Storage Health**: Checks if any physical disk reports `Unhealthy` or `Failing` $\rightarrow$ triggers `CRITICAL`.
  2. **Drive Capacity**: Evaluates every drive partition. Free space $\le 5\%$ triggers `CRITICAL`; free space $\le 15\%$ triggers `WARNING`.
  3. **RAM Check**: If total RAM $< 16.0\text{ GB}$, it records an upgrade advisory.
  4. **CPU Check**: If CPU cores $< 4$, it flags a processor upgrade recommendation.
- It assigns an overall grade: `HEALTHY`, `WARNING`, `CRITICAL`, or `UNKNOWN`.

### **Step 5: Change Detection (`HardwareChangeDetector`)**
- `InventoryService` checks if a previous snapshot exists for this specific `computer_name`.
- If a previous snapshot exists:
  - `HardwareChangeDetector` compares both snapshots using stable hardware identifiers (RAM serial/slot, Disk serial, Monitor product code, USB PNP ID, MAC address).
  - It identifies items that were **`ADDED`**, **`REMOVED`**, or **`CHANGED`** (e.g., RAM capacity increased from 8GB to 16GB).
  - It writes detected change events to `data/changes/all_changes.json` and `<ComputerName>_changes.json`.

### **Step 6: Persistence & Duplicate Prevention (`InventoryService`)**
- The system checks if a snapshot with the exact same `computer_name` and `report_date` already exists.
- If it is a duplicate, it gracefully rejects saving again and notifies the user with an informative message.
- If it is a new report:
  - Saves the full snapshot JSON to `data/snapshots/<ComputerName>/<ReportDate>.json`.
  - Saves a copy of the raw text report to `data/raw/<ComputerName>_<ReportDate>.txt`.
  - Updates the latest active snapshot in `data/normalized/<ComputerName>.json`.

### **Step 7: Rendering on Frontend (`app.py` & Jinja2 Templates)**
- When the user visits `/dashboard`:
  - `InventoryService.get_assets()` loads all active normalized records.
  - `InventoryService.get_kpis()` computes the summary totals (Total Assets, Healthy, Warnings, Criticals, Changes, Alerts, Upgrades).
  - Flask renders `templates/dashboard.html` with data injected.
  - The browser loads `style.css` for styling and `dashboard.js` for instant live table searching and status filtering.

---

## 🎓 3. Beginner's Primer: Key Python Concepts Used in this Project

If you are new to Python or intermediate web development, here are the core concepts used throughout the codebase:

### 1. Python Dataclasses (`@dataclass`)
Found in [`models/schemas.py`](file:///c:/Users/admin/PycharmProjects/AI_Inv/models/schemas.py).
```python
from dataclasses import dataclass

@dataclass
class CPUInfo:
    name: str = "N/A"
    cores: int = 4
```
*Why we use it:* Instead of writing boilerplate `__init__()`, `__repr__()`, and `__eq__()` methods manually, `@dataclass` automatically generates them for you, ensuring type safety and clean code.

### 2. Type Hints (`typing`)
Found throughout `parser/`, `services/`, and `models/`.
```python
from typing import Dict, Any, List, Optional, Tuple

def process_file(path: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
```
*Why we use it:* Tells developers and IDEs exactly what types of arguments a function expects and what it will return. `Optional[T]` means the value can either be `T` or `None`.

### 3. Regular Expressions (`re` module)
Found in [`parser/txt_parser.py`](file:///c:/Users/admin/PycharmProjects/AI_Inv/parser/txt_parser.py).
```python
import re
KEY_VALUE_PATTERN = re.compile(r"^\s*([^:]+?)\s*:\s*(.*)$")
```
*Why we use it:* Allows us to find patterns in text. `^([^:]+?)\s*:\s*(.*)$` extracts anything before the colon as Key and anything after as Value (e.g., `Computer Name : 2F-S03`).

### 4. Rotating Log Handlers (`logging.handlers.RotatingFileHandler`)
Found in [`config.py`](file:///c:/Users/admin/PycharmProjects/AI_Inv/config.py).
```python
handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
```
*Why we use it:* Prevents log files from growing infinitely and consuming hard drive space. When a log file reaches 5 MB, it rotates to `application.log.1`, keeping the 5 most recent files.

### 5. Application Factory Pattern
Found in [`app.py`](file:///c:/Users/admin/PycharmProjects/AI_Inv/app.py).
```python
def create_app() -> Flask:
    app = Flask(__name__)
    # configure routes and settings
    return app
```
*Why we use it:* Allows us to create separate app instances for automated testing (`pytest`) and live production without sharing global state or conflicting configurations.
