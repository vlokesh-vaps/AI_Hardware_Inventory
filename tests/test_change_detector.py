"""
Unit tests for Hardware Change Detector.
Validates ADDED, REMOVED, and CHANGED detection using stable identifiers.
"""
import pytest
from parser.change_detector import HardwareChangeDetector

@pytest.fixture
def detector():
    return HardwareChangeDetector()

@pytest.fixture
def baseline_snapshot():
    return {
        "asset": {
            "computer_name": "PC-001",
            "report_date": "2026-09-01 10:00:00"
        },
        "cpu": [
            {"name": "Intel Core i5-8400", "processor_id": "CPU_ID_1", "cores": 6, "threads": 6}
        ],
        "ram": [
            {"serial_number": "RAM111", "capacity_gb": 8.0, "model": "DDR4-2400", "device_locator": "DIMM1"}
        ],
        "storage": [
            {"serial_number": "DISK111", "model": "Samsung 860", "size_gb": 500.0, "media_type": "SSD", "device": "PHYSICALDRIVE0"}
        ],
        "gpu": [
            {"name": "Intel UHD Graphics 630", "manufacturer": "Intel Corporation", "video_memory": "1 GB"}
        ],
        "monitors": [
            {"serial_number": "MON111", "model": "Dell P2419H", "product_code": "DEL001", "manufacturer": "Dell"}
        ],
        "usb_devices": [
            {"pnp_device_id": "USB_DEV_1", "name": "USB Mouse", "manufacturer": "Logitech"}
        ],
        "mice": [
            {"device_id": "MOUSE_DEV_1", "name": "Optical Mouse", "description": "Standard"}
        ],
        "keyboards": [
            {"device_id": "KB_DEV_1", "name": "Standard Keyboard", "description": "USB"}
        ]
    }

def test_no_changes_on_identical_snapshots(detector, baseline_snapshot):
    """Identical consecutive snapshots should generate 0 hardware changes."""
    changes = detector.detect_changes(baseline_snapshot, baseline_snapshot)
    assert len(changes) == 0

def test_added_hardware_detection(detector, baseline_snapshot):
    """Detects newly added RAM stick, Monitor, and USB device."""
    modified = dict(baseline_snapshot)
    modified["asset"] = {"computer_name": "PC-001", "report_date": "2026-09-02 10:00:00"}
    
    # Add second RAM stick
    modified["ram"] = list(baseline_snapshot["ram"]) + [
        {"serial_number": "RAM222", "capacity_gb": 8.0, "model": "DDR4-2400", "device_locator": "DIMM2"}
    ]
    # Add second monitor
    modified["monitors"] = list(baseline_snapshot["monitors"]) + [
        {"serial_number": "MON222", "model": "LG UltraWide", "product_code": "LG002", "manufacturer": "LG"}
    ]

    changes = detector.detect_changes(baseline_snapshot, modified)
    assert len(changes) == 2

    change_types = [c["change_type"] for c in changes]
    comp_types = [c["component_type"] for c in changes]

    assert change_types == ["ADDED", "ADDED"]
    assert "RAM" in comp_types
    assert "Monitor" in comp_types

def test_removed_hardware_detection(detector, baseline_snapshot):
    """Detects removed devices (e.g. mouse unplugged, GPU removed)."""
    modified = dict(baseline_snapshot)
    modified["asset"] = {"computer_name": "PC-001", "report_date": "2026-09-02 10:00:00"}
    
    # Remove mouse
    modified["mice"] = []
    # Remove GPU
    modified["gpu"] = []

    changes = detector.detect_changes(baseline_snapshot, modified)
    assert len(changes) == 2

    assert all(c["change_type"] == "REMOVED" for c in changes)
    comp_types = [c["component_type"] for c in changes]
    assert "Mouse" in comp_types
    assert "GPU" in comp_types

def test_changed_hardware_detection(detector, baseline_snapshot):
    """Detects modified component attributes (e.g. RAM upgraded from 8GB to 16GB, CPU upgraded)."""
    modified = dict(baseline_snapshot)
    modified["asset"] = {"computer_name": "PC-001", "report_date": "2026-09-02 10:00:00"}

    # Upgrade the existing RAM stick (same slot/ID, higher capacity)
    modified["ram"] = [
        {"serial_number": "RAM111", "capacity_gb": 16.0, "model": "DDR4-3200", "device_locator": "DIMM1"}
    ]
    # Resize / upgrade storage
    modified["storage"] = [
        {"serial_number": "DISK111", "model": "Samsung 860", "size_gb": 1000.0, "media_type": "SSD", "device": "PHYSICALDRIVE0"}
    ]

    changes = detector.detect_changes(baseline_snapshot, modified)
    assert len(changes) == 2

    assert all(c["change_type"] == "CHANGED" for c in changes)
    comp_types = [c["component_type"] for c in changes]
    assert "RAM" in comp_types
    assert "Storage" in comp_types
