"""
Data schemas and type definitions for Hardware Inventory.
Provides clear structure and typing for assets, components, changes, and health status.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class AssetMetadata:
    computer_name: str = "N/A"
    ip_address: str = "N/A"
    all_ip_addresses: str = "N/A"
    manufacturer: str = "N/A"
    model: str = "N/A"
    system_type: str = "N/A"
    domain_workgroup: str = "N/A"
    logged_user: str = "N/A"
    report_date: str = "N/A"
    report_file: str = "N/A"

@dataclass
class OSInfo:
    name: str = "N/A"
    version: str = "N/A"
    build: str = "N/A"
    architecture: str = "N/A"
    serial: str = "N/A"
    install_date: str = "N/A"
    last_boot: str = "N/A"

@dataclass
class CPUInfo:
    name: str = "N/A"
    manufacturer: str = "N/A"
    model: str = "N/A"
    processor_id: str = "N/A"
    serial_number: str = "N/A"
    socket: str = "N/A"
    current_speed_mhz: Optional[int] = None
    maximum_speed_mhz: Optional[int] = None
    cores: Optional[int] = None
    threads: Optional[int] = None
    architecture: str = "N/A"
    status: str = "OK"

@dataclass
class RAMStick:
    manufacturer: str = "N/A"
    model: str = "N/A"
    serial_number: str = "N/A"
    capacity_gb: Optional[float] = None
    speed_mhz: Optional[int] = None
    configured_speed_mhz: Optional[int] = None
    device_locator: str = "N/A"
    bank_locator: str = "N/A"
    memory_type: str = "N/A"
    form_factor: str = "N/A"

@dataclass
class StorageDisk:
    device: str = "N/A"
    model: str = "N/A"
    manufacturer: str = "N/A"
    serial_number: str = "N/A"
    media_type: str = "N/A"       # e.g., SSD, HDD
    bus_type: str = "N/A"         # e.g., SATA, NVMe
    size_gb: Optional[float] = None
    health_status: str = "Healthy"
    operational_status: str = "OK"
    partitions_count: Optional[int] = None

@dataclass
class DrivePartition:
    drive_letter: str = "N/A"
    volume_name: str = "N/A"
    file_system: str = "N/A"
    total_size_gb: Optional[float] = None
    used_space_gb: Optional[float] = None
    free_space_gb: Optional[float] = None
    free_percentage: Optional[float] = None
    status: str = "NORMAL"        # NORMAL, WARNING, CRITICAL

@dataclass
class GPUInfo:
    name: str = "N/A"
    manufacturer: str = "N/A"
    driver_version: str = "N/A"
    video_memory: str = "N/A"
    video_processor: str = "N/A"
    resolution: str = "N/A"
    refresh_rate: str = "N/A"

@dataclass
class MonitorInfo:
    manufacturer: str = "N/A"
    model: str = "N/A"
    product_code: str = "N/A"
    serial_number: str = "N/A"

@dataclass
class KeyboardInfo:
    name: str = "N/A"
    description: str = "N/A"
    manufacturer: str = "N/A"
    device_id: str = "N/A"
    status: str = "OK"

@dataclass
class MouseInfo:
    name: str = "N/A"
    description: str = "N/A"
    manufacturer: str = "N/A"
    device_id: str = "N/A"
    hardware_type: str = "N/A"
    status: str = "OK"

@dataclass
class USBDeviceInfo:
    name: str = "N/A"
    manufacturer: str = "N/A"
    device_id: str = "N/A"
    pnp_device_id: str = "N/A"
    status: str = "OK"

@dataclass
class NetworkAdapterInfo:
    name: str = "N/A"
    manufacturer: str = "N/A"
    mac_address: str = "N/A"
    adapter_type: str = "N/A"
    speed: str = "N/A"
    device_id: str = "N/A"
    status: str = "OK"

@dataclass
class MotherboardInfo:
    manufacturer: str = "N/A"
    model: str = "N/A"
    version: str = "N/A"
    serial_number: str = "N/A"
    part_number: str = "N/A"
    status: str = "OK"

@dataclass
class BIOSInfo:
    manufacturer: str = "N/A"
    bios_version: str = "N/A"
    bios_version_2: str = "N/A"
    serial_number: str = "N/A"
    release_date: str = "N/A"
    smbios_major: str = "N/A"
    smbios_minor: str = "N/A"

@dataclass
class HardwareChange:
    date: str
    computer_name: str
    component_type: str
    change_type: str              # ADDED, REMOVED, CHANGED
    description: str
    previous_value: str
    current_value: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class UpgradeRecommendation:
    component: str
    reason: str
    current_value: str
    recommended_action: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class HealthStatus:
    overall: str = "HEALTHY"      # HEALTHY, WARNING, CRITICAL, UNKNOWN
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    storage_alert_count: int = 0
    upgrade_required_count: int = 0
    recommendations: List[UpgradeRecommendation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["recommendations"] = [r.to_dict() if hasattr(r, "to_dict") else r for r in self.recommendations]
        return d
