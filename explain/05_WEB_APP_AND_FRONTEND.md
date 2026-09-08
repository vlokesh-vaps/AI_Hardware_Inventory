# Chapter 5: Web Application, API & Frontend Interface

This document explains the Flask web server, REST API endpoints, Jinja2 templating system, CSS design system, and Vanilla JavaScript interactivity.

---

## 🌐 1. Flask Web Server: `app.py` & `main.py`

### 🎯 Application Factory Pattern (`create_app()`, Lines 28–313)
Instead of creating a global `app = Flask(__name__)` instance at import time, `create_app()` acts as an **Application Factory**:
```python
def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    inventory_service = InventoryService()
    ...
    return app
```
*Why this matters:* It allows test runners like `pytest` to instantiate clean, isolated test clients with testing configurations without interfering with production state.

---

### 🛣️ Web Routes Breakdown

#### 1. Dashboard: `GET /` & `GET /dashboard` (Lines 43–63)
- Calls `inventory_service.get_assets()`, `get_kpis()`, `get_changes()[:6]`, and `get_storage_alerts()`.
- Renders `dashboard.html`, injecting assets, summary counts, recent activity, and storage alerts.

#### 2. PC Details: `GET /pc/<computer_name>` (Lines 64–97)
- Loads the computer's latest snapshot using `inventory_service.get_latest_snapshot(computer_name)`.
- If the computer does not exist, flashes a warning and redirects to `/dashboard`.
- Loads historical snapshot logs via `inventory_service.get_snapshot_history(computer_name)`.
- Renders `pc_details.html` with full hardware specs (CPU, RAM, Disks, Drives, GPU, Displays, USB, Network, Motherboard, BIOS, Installed Software).

#### 3. Hardware Changes: `GET /changes` (Lines 98–115)
- Extracts query parameters: `request.args.get("computer")`, `request.args.get("component")`, `request.args.get("change_type")`, `request.args.get("date")`.
- Calls `inventory_service.get_changes(filters)`.
- Renders `changes.html` with filtered change events.

#### 4. Storage & Alerts: `GET /alerts` (Lines 116–122)
- Renders `alerts.html` with partitions below capacity thresholds and actionable upgrade recommendations.

#### 5. File Upload: `POST /upload` (Lines 129–190)
- Reads uploaded files using `request.files.getlist("files")`.
- Iterates over each file, validates `.txt` extension, saves to `uploads/`, and calls `inventory_service.process_report_file()`.
- Summarizes successful imports, duplicate reports, and any errors using Flask `flash()` toasts.

#### 6. Directory Import: `POST /import-dir` (Lines 191–228)
- Reads `dir_path` from form input (default `C:\healthcheck`).
- Scans all `*.txt` files in the specified folder, processes each, and redirects with a batch summary toast.

---

### 🔌 REST API Endpoints (Lines 230–295)

The application provides JSON endpoints for headless automation:

| Endpoint | Method | Response Description |
| :--- | :---: | :--- |
| `/api/assets` | `GET` | Returns list of all computers with latest specs and health status. |
| `/api/assets/<name>` | `GET` | Returns full specifications and historical snapshot list for one machine. |
| `/api/changes` | `GET` | Returns JSON change events with optional query string filters. |
| `/api/alerts` | `GET` | Returns storage partition alerts and upgrade advisories. |
| `/api/upload` | `POST` | Accepts `multipart/form-data` file uploads and returns JSON ingestion status. |

---

## 🎨 2. Frontend Templates & CSS

### 🧱 Jinja2 Template Inheritance: `templates/base.html`
All web pages extend `base.html`. This ensures a single top navigation bar, notification toast container, and footer across the entire application:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <title>{% block title %}Hardware Inventory{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body>
    <header class="navbar"> ... </header>
    <div class="toast-container"> ... </div>
    <main class="main-content">
        {% block content %}{% endblock %}
    </main>
    <footer class="footer"> ... </footer>
</body>
</html>
```

---

### 🎨 Enterprise Design System: `static/css/style.css`
Defined using modern CSS custom properties (`:root`):
- **Background**: Soft modern slate `#f8fafc`.
- **Cards**: Crisp white `#ffffff` with subtle borders `#e2e8f0` and soft elevation shadows.
- **Typography**: Inter font family for clean readability.
- **Status Color Coding**:
  - `HEALTHY`: Emerald Green (`bg: #ecfdf5`, `text: #065f46`, `dot: #10b981`)
  - `WARNING`: Amber (`bg: #fffbeb`, `text: #92400e`, `dot: #f59e0b`)
  - `CRITICAL`: Crimson Red (`bg: #fef2f2`, `text: #991b1b`, `dot: #ef4444`)
  - `ADDED`: Blue (`#3b82f6`)
  - `REMOVED`: Red (`#ef4444`)
  - `CHANGED`: Purple (`#8b5cf6`)

---

## ⚡ 3. Client-Side Interactivity: `static/js/dashboard.js`

The application uses **Vanilla JavaScript** (no external framework overhead) to provide snappy client-side features:

### 1. Live PC Table Search & Status Filtering (`initPcTableFilters()`)
Each row in the PC table contains metadata attributes:
```html
<tr class="clickable-row" data-health="HEALTHY" data-search="2F-S03 192.168.1.100 Dell OptiPlex">
```
As the user types in `#pc-search-input` or clicks the health filter buttons (All, Healthy, Warning, Critical), JavaScript immediately filters the rows without reloading the page.

### 2. Live USB & Software Filtering (`initUsbFilter()` & `initSoftwareFilter()`)
Allows instant searching through connected USB peripherals and the 270+ installed software applications.

### 3. Collapsible Software Drawer (`toggleSection()`)
Installed software is hidden by default in `pc_details.html` to keep the hardware view clean. Clicking the drawer expands the table smoothly and updates the button label to `Hide Applications ↑`.

### 4. Drag-and-Drop File Upload (`initDropzone()`)
Listens for HTML5 `dragover`, `dragleave`, and `drop` events on `#dropzone`. When files are dropped, it attaches them to the hidden `<input type="file">` element, formats file sizes in KB, and displays a ready-to-ingest file list.

### 5. Auto-Dismissing Toast Alerts (`initToastAutoDismiss()`)
Success and warning notification banners automatically fade out smoothly after 6 seconds and remove themselves from the DOM.
