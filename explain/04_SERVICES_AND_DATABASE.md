# Chapter 4: Services, Repository Pattern & Configuration

This document explains the data access layer, persistence strategies, configuration management, and dataclass schemas.

---

## 🗄️ 1. The Inventory Repository Service: `services/inventory_service.py`

### 🎯 Why the Repository Pattern?
Instead of reading and writing files directly inside Flask route functions, `InventoryService` acts as a **mediator** between the application logic and the storage system.

If the organization decides to replace JSON files with **PostgreSQL**, **MongoDB**, or **SQLite**, only `inventory_service.py` needs to be updated. All parsers, change detectors, API endpoints, and web templates remain completely untouched!

---

### 🔍 Key Methods Breakdown

#### 1. `process_report_file()` (Lines 40–75)
Orchestrates the complete ingestion pipeline:
```python
def process_report_file(self, content_or_path, filename):
    # 1. Parse raw report text
    raw_data = self.parser.parse(content_or_path)

    # 2. Normalize and cast types
    normalized_data = self.normalizer.normalize(raw_data, original_filename=filename)

    # 3. Calculate health scoring & recommendations
    health = self.health_service.evaluate_health(normalized_data)
    normalized_data["health"] = health

    # 4. Save snapshot & detect hardware modifications
    success, msg, changes = self.save_snapshot(normalized_data, raw_text, filename)
    return success, msg, normalized_data
```

---

#### 2. `save_snapshot()` & Duplicate Prevention (Lines 77–131)
- **Path Sanitization**: `_sanitize_filename("2026-09-03 17:51:08")` converts illegal Windows characters (`:`, `\`, `/`) into underscores (`2026-09-03 17_51_08`).
- **Duplicate Snapshot Policy**:
  ```python
  if snapshot_file.exists():
      return False, f"Duplicate snapshot: Report for {comp_name} on {report_date} has already been imported.", []
  ```
  *Why:* Prevents duplicate reports from corrupting change logs or creating duplicate entries.
- **Change Detection Trigger**:
  Fetches `prev_snapshot = self.get_latest_snapshot(comp_name)` before writing the new snapshot, passes both to `HardwareChangeDetector`, and saves any detected changes.
- **Three-Tier Storage Persistence**:
  1. `data/snapshots/<ComputerName>/<Date>.json`: Historical audit archive.
  2. `data/raw/<ComputerName>_<Date>.txt`: Exact copy of the original raw report.
  3. `data/normalized/<ComputerName>.json`: Latest active state of the computer.

---

#### 3. `get_assets()` & `get_kpis()` (Lines 214–233, 303–333)
- `get_assets()`: Scans `data/normalized/*.json` to return a list of all active computers in the organization, sorted alphabetically.
- `get_kpis()`: Computes real-time counts across all assets for the 7 dashboard cards:
  - `total_assets`: Total monitored machines.
  - `healthy`: Count of machines with `HEALTHY` status.
  - `warning`: Count of machines with `WARNING` status.
  - `critical`: Count of machines with `CRITICAL` status.
  - `hardware_changes`: Total detected change events.
  - `storage_alerts`: Number of partitions with low space ($\le 15\%$).
  - `upgrade_required`: Total upgrade advisories across all machines.

---

#### 4. `get_changes()` with Multi-Field Filtering (Lines 235–263)
Loads `data/changes/all_changes.json` and filters dynamically by:
- `computer_name`: Partial case-insensitive search (e.g. `"2f"` matches `"2F-S03"`).
- `component_type`: Component match (e.g. `"RAM"`, `"Storage"`, `"GPU"`).
- `change_type`: `"ADDED"`, `"REMOVED"`, or `"CHANGED"`.
- `date`: Substring date filter (e.g. `"2026-09"`).

---

## ⚙️ 2. Centralized Configuration: `config.py`

### 🎯 Purpose
Provides a single source of truth for all paths, alert thresholds, file upload limits, and logging setup.

```python
# 1. Directory Structure
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
NORMALIZED_DIR = DATA_DIR / "normalized"
CHANGES_DIR = DATA_DIR / "changes"
UPLOADS_DIR = BASE_DIR / "uploads"
LOGS_DIR = BASE_DIR / "logs"

# Ensure all directories exist automatically on startup
for directory in [DATA_DIR, RAW_DIR, SNAPSHOTS_DIR, NORMALIZED_DIR, CHANGES_DIR, UPLOADS_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# 2. Configurable Health Thresholds
LOW_STORAGE_WARNING_PERCENT = 15.0   # Free space <= 15% triggers Warning
LOW_STORAGE_CRITICAL_PERCENT = 5.0   # Free space <= 5% triggers Critical
RECOMMENDED_MIN_RAM_GB = 16.0        # < 16 GB triggers RAM upgrade recommendation
RECOMMENDED_MIN_CPU_CORES = 4        # < 4 cores triggers CPU upgrade recommendation
```

### 📝 Rotating Logger Setup (Lines 38–60)
```python
def setup_logger(name: str, log_file: Path, level: int = logging.INFO) -> logging.Logger:
    handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    ...
```
Creates dedicated loggers:
- `app_logger` $\rightarrow$ `logs/application.log`
- `parser_logger` $\rightarrow$ `logs/parser.log`
- `change_logger` $\rightarrow$ `logs/change_detector.log`
- `error_logger` $\rightarrow$ `logs/error.log`

---

## 📐 3. Data Schemas: `models/schemas.py`

### 🎯 Purpose
Defines typed `@dataclass` structures that represent the data contracts used throughout the system.

### Key Dataclasses:
1. **`AssetMetadata`**: Top-level computer info (`computer_name`, `ip_address`, `manufacturer`, `model`, `report_date`).
2. **`CPUInfo`**: Processor specs (`name`, `socket`, `cores`, `threads`, `current_speed_mhz`, `status`).
3. **`RAMStick`**: Individual memory module (`manufacturer`, `model`, `capacity_gb`, `speed_mhz`, `device_locator`, `serial_number`).
4. **`StorageDisk`**: Physical disk (`device`, `model`, `serial_number`, `media_type`, `size_gb`, `health_status`, `operational_status`).
5. **`DrivePartition`**: Partition volume (`drive_letter`, `volume_name`, `file_system`, `total_size_gb`, `free_space_gb`, `free_percentage`, `status`).
6. **`HardwareChange`**: Log event (`date`, `computer_name`, `component_type`, `change_type`, `description`, `previous_value`, `current_value`).
7. **`UpgradeRecommendation`**: Advisory (`component`, `reason`, `current_value`, `recommended_action`).
8. **`HealthStatus`**: Overall health score (`overall`, `issues`, `warnings`, `storage_alert_count`, `upgrade_required_count`, `recommendations`).
