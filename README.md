# Hardware Inventory & Health Check Dashboard

An enterprise IT asset management and health check analysis platform built with **Python**, **Flask**, **Jinja2**, and **Vanilla JavaScript**. 

The application automatically ingests, parses, and normalizes Windows health-check `.txt` reports, tracks hardware modifications across snapshots over time, monitors storage and disk health thresholds, generates upgrade advisories, and presents an interactive web dashboard.

---

## 📑 Table of Contents

- [Key Features](#-key-features)
- [Project Architecture & Directory Structure](#-project-architecture--directory-structure)
- [System Requirements](#-system-requirements)
- [Installation & Quickstart](#-installation--quickstart)
- [Running the Application](#-running-the-application)
- [Web Interface Pages](#-web-interface-pages)
- [REST API Endpoints](#-rest-api-endpoints)
- [Configuration & Alert Thresholds](#-configuration--alert-thresholds)
- [Hardware Change Detection Logic](#-hardware-change-detection-logic)
- [Health Scoring & Recommendation Rules](#-health-scoring--recommendation-rules)
- [Running Automated Tests](#-running-automated-tests)
- [Logging System](#-logging-system)
- [License](#-license)

---

## ✨ Key Features

- **Header-Based Section Parser**: Independent of line numbers; parses 15+ sections including CPU, RAM, Physical Storage, Storage Health, Drive Space, GPUs, Displays, USB Devices, Network Adapters, Motherboard, BIOS, and Installed Software.
- **Hardware Change Tracking**: Uses stable component identifiers (serial numbers, device locators, PNP IDs, MAC addresses) to detect `ADDED`, `REMOVED`, and `CHANGED` hardware events between consecutive snapshots.
- **Proactive Health Scoring**: Categorizes machine health as `HEALTHY`, `WARNING`, `CRITICAL`, or `UNKNOWN` based on drive free space percentages, disk SMART health status, and hardware errors.
- **Actionable Upgrade Recommendations**: Automatically flags systems with low RAM (< 16 GB), low CPU cores (< 4 cores), or low partition space, providing specific upgrade guidance.
- **Clean Enterprise Dashboard**:
  - 7 KPI summary cards (Total Assets, Healthy, Warning, Critical, Changes, Storage Alerts, Upgrade Required).
  - PC Inventory table with real-time text search and health status filtering.
  - Interactive PC Details page with dedicated spec cards and a collapsible drawer for installed software applications (e.g., 270+ software items).
- **Flexible Report Ingestion**:
  - Drag-and-drop multi-file upload with progress feedback.
  - Local/network folder batch scanning (e.g., `C:\healthcheck`).
  - REST API endpoint for automated scripts and scheduled agents.
  - Duplicate snapshot prevention to avoid data redundancy.
- **Repository Pattern**: Filesystem-isolated JSON snapshot storage designed for future migration to PostgreSQL or SQLite with zero UI/parser changes.

---

## 📂 Project Architecture & Directory Structure

```text
AI_Inv/
├── app.py                      # Flask application factory, web routes, API endpoints, error handlers
├── config.py                   # Centralized configuration, thresholds, directory paths, rotating loggers
├── main.py                     # Primary entry point to launch the web server
├── requirements.txt            # Python dependencies (Flask, pytest)
├── README.md                   # Project documentation and guide
│
├── parser/                     # Parsing and normalizer engine
│   ├── __init__.py
│   ├── txt_parser.py           # Robust section & key-value extractor for health check reports
│   ├── normalizer.py           # Canonical schema converter, unit parser, disk-to-health merger
│   └── change_detector.py      # Hardware modification engine using stable component IDs
│
├── services/                   # Business logic and data access layer
│   ├── __init__.py
│   ├── inventory_service.py    # Repository service (snapshots, assets, change logs, KPIs)
│   └── health_service.py       # Health scoring, storage alerts, and upgrade recommendations
│
├── models/                     # Data structures and schemas
│   ├── __init__.py
│   └── schemas.py              # Dataclasses for Assets, Specs, Changes, Recommendations, Health
│
├── templates/                  # Jinja2 HTML templates
│   ├── base.html               # Base layout, navbar, footer, toast notifications
│   ├── dashboard.html          # Main dashboard, KPI cards, PC inventory table, recent widgets
│   ├── pc_details.html         # Individual computer specs, disk utilization, USB & software drawer
│   ├── changes.html            # Dedicated hardware change audit log with multi-field filters
│   ├── alerts.html             # Storage capacity alerts and upgrade recommendation list
│   └── upload.html             # Multi-file drag-and-drop upload and folder import interface
│
├── static/                     # Frontend assets
│   ├── css/
│   │   └── style.css           # Modern, enterprise-grade responsive CSS (light theme)
│   └── js/
│       └── dashboard.js        # Live search, table filters, drag-and-drop, UI accordion toggling
│
├── data/                       # Application data store
│   ├── raw/                    # Original TXT report archive (<ComputerName>_<Date>.txt)
│   ├── snapshots/              # Historical JSON snapshots (<ComputerName>/<Date>.json)
│   ├── normalized/             # Latest normalized JSON record per machine (<ComputerName>.json)
│   └── changes/                # Global and per-machine hardware change logs (all_changes.json)
│
├── uploads/                    # Temporary staging directory for uploaded reports
│
├── logs/                       # Rotating application log files
│   ├── application.log         # General application lifecycle and web request events
│   ├── parser.log              # Report parsing and normalization logs
│   ├── change_detector.log     # Detailed hardware change detection logs
│   └── error.log               # Warnings and application exceptions
│
└── tests/                      # Automated test suite (pytest)
    ├── __init__.py
    ├── test_parser.py          # Unit tests for txt_parser and normalizer
    ├── test_change_detector.py # Unit tests for ADDED/REMOVED/CHANGED hardware detection
    ├── test_health.py          # Unit tests for health rules, storage thresholds, recommendations
    └── test_routes.py          # Integration tests for Flask web routes and REST API endpoints
```

---

## 💻 System Requirements

- **Operating System**: Windows, Linux, or macOS
- **Python**: Python 3.10 or higher
- **Web Browser**: Any modern browser (Chrome, Edge, Firefox, Safari)

---

## 🚀 Installation & Quickstart

### 1. Clone or Navigate to the Project

```bash
cd c:\Users\admin\PycharmProjects\AI_Inv
```

### 2. Set Up a Virtual Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (cmd.exe):
.venv\Scripts\activate.bat
# Linux/macOS:
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 🏃 Running the Application

### Start via Entry Point:

```bash
python main.py
```

or using `app.py`:

```bash
python app.py
```

Once started, open your web browser and navigate to:

👉 **`http://127.0.0.1:5000`**

---

## 🌐 Web Interface Pages

| Route | Page Name | Description |
| :--- | :--- | :--- |
| `GET /` or `GET /dashboard` | **Dashboard** | KPI cards, active PC inventory with live search & health filtering, recent hardware changes, and drive capacity alerts. |
| `GET /pc/<computer_name>` | **PC Details** | Detailed system profile, OS specs, CPU cores/clocks, RAM slot table, physical disks, partition space bars, GPUs, displays, input devices, network adapters, USB device search table, collapsible installed software drawer, and snapshot history. |
| `GET /changes` | **Hardware Changes** | Complete hardware modification audit log with filters for Computer Name, Component Type, Change Type (`ADDED`, `REMOVED`, `CHANGED`), and Date. |
| `GET /alerts` | **Storage & Alerts** | Drive space utilization monitoring with threshold warnings and proactive hardware upgrade advisories. |
| `GET /upload` | **Upload Reports** | Drag-and-drop multi-file upload zone and local folder batch import tool (e.g. `C:\healthcheck`). |

---

## 🔌 REST API Endpoints

The system provides RESTful JSON endpoints for automation scripts and remote monitoring:

### 1. List All Assets
- **Endpoint**: `GET /api/assets`
- **Response**:
```json
{
  "count": 2,
  "assets": [
    {
      "asset": {
        "computer_name": "2F-S03",
        "ip_address": "192.168.1.100",
        "manufacturer": "Dell Inc.",
        "model": "OptiPlex 7060",
        "report_date": "2026-09-03 17:51:08"
      },
      "health": {
        "overall": "HEALTHY",
        "issues": [],
        "warnings": []
      },
      "total_ram_gb": 23.8
    }
  ]
}
```

### 2. Get Single PC Snapshot & History
- **Endpoint**: `GET /api/assets/<computer_name>`
- **Response**: Returns the latest complete specification JSON together with historical snapshot timestamps.

### 3. Get Hardware Changes Log
- **Endpoint**: `GET /api/changes`
- **Query Parameters (Optional)**: `?computer=2F-S03&component=RAM&change_type=ADDED&date=2026-09`
- **Response**:
```json
{
  "count": 1,
  "changes": [
    {
      "date": "2026-09-03 17:56:27",
      "computer_name": "2F-S03",
      "component_type": "RAM",
      "change_type": "ADDED",
      "description": "Added RAM: 8.0 GB DDR4-2666 (DIMM2, S/N: RAM_SN_002)",
      "previous_value": "N/A",
      "current_value": "8.0 GB DDR4-2666 (DIMM2, S/N: RAM_SN_002)"
    }
  ]
}
```

### 4. Get Storage & Upgrade Alerts
- **Endpoint**: `GET /api/alerts`
- **Response**: Returns arrays of `storage_alerts` and `upgrade_recommendations`.

### 5. Automated File Ingestion via API
- **Endpoint**: `POST /api/upload`
- **Body**: `multipart/form-data` with one or more files in the `file` or `files` field.
- **Response**:
```json
{
  "processed": 1,
  "results": [
    {
      "filename": "2F-S03_report.txt",
      "success": true,
      "message": "Successfully processed report for 2F-S03. 0 changes detected.",
      "computer_name": "2F-S03"
    }
  ]
}
```

---

## ⚙️ Configuration & Alert Thresholds

Configurable in [`config.py`](file:///c:/Users/admin/PycharmProjects/AI_Inv/config.py):

| Setting | Default Value | Description |
| :--- | :---: | :--- |
| `LOW_STORAGE_WARNING_PERCENT` | `15.0%` | Partitions with $\le$ 15% free space trigger a **WARNING** status. |
| `LOW_STORAGE_CRITICAL_PERCENT` | `5.0%` | Partitions with $\le$ 5% free space trigger a **CRITICAL** status. |
| `RECOMMENDED_MIN_RAM_GB` | `16.0 GB` | Machines with < 16 GB total RAM receive an upgrade recommendation. |
| `RECOMMENDED_MIN_CPU_CORES` | `4 Cores` | Machines with < 4 physical cores receive a processor upgrade advisory. |
| `MAX_CONTENT_LENGTH` | `32 MB` | Maximum allowed report upload payload size. |
| `ALLOWED_EXTENSIONS` | `{"txt"}` | Permitted report file formats. |

---

## 🔍 Hardware Change Detection Logic

When a new report is processed for a computer, the `HardwareChangeDetector` compares it against the previous recorded snapshot using stable hardware identifiers:

| Component | Primary Identifier | Fallback Identifier |
| :--- | :--- | :--- |
| **RAM** | `serial_number` | `device_locator` |
| **Storage Disks** | `serial_number` | `device` path + `model` |
| **Monitors / Displays** | `serial_number` | `model` + `product_code` |
| **GPU / Video** | `name` + `manufacturer` | `name` |
| **USB Devices** | `pnp_device_id` | `device_id` |
| **Network Adapters** | `mac_address` | `name` |
| **CPU** | `processor_id` | `name` |
| **Keyboards / Mice** | `device_id` | `name` |

### Change Types:
- **`ADDED`**: Component found in current snapshot but missing from previous snapshot.
- **`REMOVED`**: Component found in previous snapshot but missing from current snapshot.
- **`CHANGED`**: Component exists in both snapshots, but key physical attributes changed (e.g. RAM capacity changed, Disk resized, CPU clock speed or core count updated).

---

## 🩺 Health Scoring & Recommendation Rules

1. **`CRITICAL`**:
   - Any physical storage disk reporting `Unhealthy`, `Failing`, `Degraded`, or `Error`.
   - Any partition with free disk space $\le$ `5.0%`.
   - Hardware operational errors reported for CPU or Motherboard.
2. **`WARNING`**:
   - Any partition with free space between `5.0%` and `15.0%`.
   - Total system RAM < `16.0 GB`.
   - CPU core count < `4 Cores`.
3. **`HEALTHY`**:
   - All physical disks healthy and operational.
   - All partitions have > `15.0%` free space.
   - System meets recommended memory and processor thresholds.
4. **`UNKNOWN`**:
   - Insufficient hardware data in report to evaluate health.

---

## 🧪 Running Automated Tests

The codebase includes an automated test suite verifying parsers, change detectors, health rules, and web routes.

To run all tests:

```bash
pytest
```

To run tests with detailed verbosity:

```bash
pytest -v
```

### Test Coverage Summary:
- [`tests/test_parser.py`](file:///c:/Users/admin/PycharmProjects/AI_Inv/tests/test_parser.py): Validates extraction of all sections from synthetic and real reports, empty file handling, and missing fields.
- [`tests/test_change_detector.py`](file:///c:/Users/admin/PycharmProjects/AI_Inv/tests/test_change_detector.py): Validates detection of `ADDED`, `REMOVED`, and `CHANGED` hardware events and identical snapshot comparisons.
- [`tests/test_health.py`](file:///c:/Users/admin/PycharmProjects/AI_Inv/tests/test_health.py): Validates health calculations, drive threshold triggers, and upgrade recommendation engines.
- [`tests/test_routes.py`](file:///c:/Users/admin/PycharmProjects/AI_Inv/tests/test_routes.py): Validates all web UI routes, 404 redirects, and REST API JSON responses.

---

## 📝 Logging System

The application logs all activity to rotating files in `logs/`:

- **`logs/application.log`**: Web server requests, snapshot saves, and system status.
- **`logs/parser.log`**: Parsing operations, section detection, and normalization summaries.
- **`logs/change_detector.log`**: Snapshot comparison operations and detected hardware events.
- **`logs/error.log`**: Application warnings, unhandled exceptions, and error stack traces.

---

## 📄 License

This project is licensed under the MIT License.
