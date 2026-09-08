# Chapter 2: Deep Dive into Parser & Data Normalizer

This document breaks down how raw, unstructured Windows text reports are converted into clean, validated, and normalized Python data structures.

---

## 🛠️ 1. The Parser: `parser/txt_parser.py`

### 🎯 Purpose
Windows health-check reports are generated as plain text files with varying formats, dividers like `========================`, and repeated sections (e.g. multiple RAM sticks or physical disks). 

The `TxtParser` class converts this freeform text into a structured raw dictionary **without relying on hardcoded line numbers**.

---

### 🔍 Key Patterns & Variables (Lines 13–56)

```python
SECTION_DIVIDER_PATTERN = re.compile(r"^={10,}|^-{10,}")
KEY_VALUE_PATTERN = re.compile(r"^\s*([^:]+?)\s*:\s*(.*)$")
NUMBERED_ITEM_PATTERN = re.compile(r"^(RAM STICK|DISK|CPU|MONITOR|SOFTWARE)\s+#(\d+)", re.IGNORECASE)
DRIVE_ITEM_PATTERN = re.compile(r"^DRIVE:\s*([A-Za-z]:)", re.IGNORECASE)
```

1. **`SECTION_DIVIDER_PATTERN`**: Matches divider bars like `========================================` (at least 10 equal or hyphen signs).
2. **`KEY_VALUE_PATTERN`**: Matches any line with `Key : Value`. It captures everything before the `:` as the key and everything after as the value.
3. **`NUMBERED_ITEM_PATTERN`**: Detects numbered sub-items, such as `RAM STICK #1`, `DISK #2`, `MONITOR #1`.
4. **`DRIVE_ITEM_PATTERN`**: Matches drive partition headers like `DRIVE: C:`.
5. **`SECTION_MAP`**: A dictionary mapping messy text titles (e.g. `"physical storage / hdd / ssd"`) into canonical dictionary keys (`"physical_disks"`).

---

### 🔍 Main Parsing Method: `parse()` (Lines 58–152)

```python
def parse(self, content_or_path: Union[str, Path]) -> Dict[str, Any]:
```

#### Step 1: Input Validation
- Checks if the input is a file path on disk or an in-memory string.
- If it's a file, reads it using UTF-8 with `errors="replace"` to prevent crashing on unusual binary characters.
- If the file is empty or contains only whitespace, raises a descriptive `ValueError("The report file is empty.")`.

#### Step 2: Header Parsing (Before the first section)
- Loops through the top lines of the file (before the first major divider).
- Extracts top-level metadata like `IP Address`, `Computer Name`, `Report Date`.

#### Step 3: Section Identification State Machine
- Scans each line for `SECTION_DIVIDER_PATTERN`.
- When a divider is found, it **peeks** at the next non-empty line.
- If the peeked line matches a known section title in `SECTION_MAP`:
  1. It saves all lines accumulated for the previous section.
  2. It switches `current_section_name` to the new section.
  3. It skips the title line and trailing dividers to continue reading content.

---

### 🔍 Section Handlers: `_parse_single_item_section` & `_parse_multi_item_section` (Lines 154–252)

Different sections have different structures:

1. **Single-Item Sections** (e.g., `Motherboard`, `BIOS`, `Operating System`):
   - Only contain a single set of key-value pairs.
   - `_parse_single_item_section()` iterates over the lines, regex matches `Key : Value`, and returns a simple dictionary `{"Manufacturer": "HP", "Model": "843B"}`.

2. **Multi-Item Sections** (e.g., `RAM`, `Physical Storage`, `GPU`, `USB Devices`, `Installed Software`):
   - Contain multiple repeated hardware items (e.g., RAM Stick 1, RAM Stick 2).
   - `_parse_multi_item_section()` acts as an accumulator:
     - When it sees `RAM STICK #1`, `DISK #1`, `GPU`, or `USB Device`, it closes the previous item and appends it to `items`.
     - It creates a new `current_item = {}` and begins storing key-value pairs for that specific device.
     - At the end of the section, it returns:
       ```python
       {
           "meta": {"Number of RAM Sticks": "2"},
           "items": [
               {"Capacity": "8 GB", "Speed": "2666 MHz", "Device Locator": "DIMM1"},
               {"Capacity": "8 GB", "Speed": "2666 MHz", "Device Locator": "DIMM2"}
           ]
       }
       ```

---

## 🧹 2. The Normalizer: `parser/normalizer.py`

### 🎯 Purpose
The raw dictionary from `TxtParser` contains raw string strings like `"16.0 GB"`, `"3192 MHz"`, `"Healthy"`, or missing fields.

`DataNormalizer` standardizes these strings into clean, typed Python dictionaries (integers, floats, standard strings, and merged data objects).

---

### 🔍 Numeric & String Sanitizers (Lines 16–56)

1. **`_parse_float(value)`**:
   - Uses regex `[-+]?\d*\.?\d+` to safely extract floating-point numbers.
   - Example: `"465.76 GB"` $\rightarrow$ `465.76`
   - Example: `"56.98 %"` $\rightarrow$ `56.98`
   - Returns `None` if no number exists.

2. **`_parse_int(value)`**:
   - Uses regex `[-+]?\d+` to safely extract integer numbers.
   - Example: `"3200 MHz"` $\rightarrow$ `3200`
   - Example: `"6 Cores"` $\rightarrow$ `6`

3. **`_clean_str(value, default="N/A")`**:
   - Strips leading/trailing whitespace.
   - Returns `"N/A"` if the value is `None`, empty, or missing.

---

### 🔍 Step-by-Step Normalization Logic (`normalize()`, Lines 58–385)

#### 1. Asset Metadata (Lines 63–91)
- Extracts `computer_name`, `ip_address`, `manufacturer`, `model`, `system_type`, `domain_workgroup`, `logged_user`, `report_date`, and `report_file`.
- Provides fallback logic: if `computer_name` is missing from the header, it checks the OS section or extracts it from the filename (e.g. `2F-S03_2026.txt` $\rightarrow$ `2F-S03`).

#### 2. Physical Storage & Health Merger (Lines 150–213)
In the raw report, physical disk specifications (Model, Size, Bus) and SMART Health (Healthy, Operational Status) are reported in two separate sections: `PHYSICAL STORAGE` and `STORAGE HEALTH`.

`DataNormalizer` intelligently joins them:
```python
# Create lookup indexes for storage health by Serial Number and Model
health_by_serial = {h["Serial Number"].lower(): h for h in raw_health}
health_by_model = {h["Model"].lower(): h for h in raw_health}

for disk in raw_disks:
    # Match health status by Serial Number or Model
    h_info = health_by_serial.get(serial) or health_by_model.get(model)
    
    storage_item = {
        "device": disk.get("Device"),
        "model": disk.get("Model"),
        "serial_number": serial,
        "media_type": "SSD" if "ssd" in str(h_info.get("Media Type")).lower() else "HDD",
        "size_gb": _parse_float(disk.get("Size")),
        "health_status": h_info.get("Health Status", "Healthy") if h_info else "Healthy",
        "operational_status": h_info.get("Operational Status", "OK") if h_info else "OK"
    }
    storage.append(storage_item)
```
*Result:* Each disk in the normalized record has both hardware attributes (size, serial, bus) and health status (Healthy, OK).

#### 3. Drive Space & Utilization Status (Lines 215–245)
- Extracts `total_size_gb`, `used_space_gb`, `free_space_gb`, and `free_percentage`.
- If `free_percentage` is missing, it automatically calculates:
  $$\text{free\_percentage} = \left(\frac{\text{free\_space\_gb}}{\text{total\_size\_gb}}\right) \times 100$$
- Classifies each partition:
  - $\le 5.0\% \rightarrow$ `"CRITICAL"`
  - $\le 15.0\% \rightarrow$ `"WARNING"`
  - $> 15.0\% \rightarrow$ `"NORMAL"`

#### 4. Installed Software Segregation (Lines 347–357)
- Large reports often contain 270+ software items.
- If placed directly inside general hardware specs, they would clutter the data model.
- `DataNormalizer` collects them in `installed_software` and computes `software_count = len(software_list)`, enabling clean collapsible rendering on the frontend.
