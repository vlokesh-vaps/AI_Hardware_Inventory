"""
Data Normalizer for Hardware Inventory.
Transforms raw parsed dictionaries into standardized, type-safe structures.
"""
import re
from typing import Dict, Any, List, Optional
from config import (
    parser_logger, 
    LOW_STORAGE_WARNING_PERCENT, 
    LOW_STORAGE_CRITICAL_PERCENT
)

class DataNormalizer:
    """Standardizes parsed report sections into a clean internal data model."""

    @staticmethod
    def _parse_float(value: Any) -> Optional[float]:
        """Extracts float value from strings like '23.8 GB', '953.87 GB', '23.24 %'."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        val_str = str(value).replace(",", "").strip()
        match = re.search(r"[-+]?\d*\.?\d+", val_str)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_int(value: Any) -> Optional[int]:
        """Extracts integer value from strings like '3192 MHz', '6', '12'."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        val_str = str(value).replace(",", "").strip()
        match = re.search(r"[-+]?\d+", val_str)
        if match:
            try:
                return int(match.group(0))
            except ValueError:
                return None
        return None

    @staticmethod
    def _clean_str(value: Any, default: str = "N/A") -> str:
        """Strips whitespace and returns a clean string or default."""
        if value is None:
            return default
        s = str(value).strip()
        return s if s else default

    def normalize(self, raw_data: Dict[str, Any], original_filename: str = "") -> Dict[str, Any]:
        """Converts raw parsed data dict into canonical normalized JSON structure."""
        header = raw_data.get("header", {})
        sections = raw_data.get("sections", {})

        # 1. Asset Metadata
        comp_os = sections.get("computer_os", {})
        comp_name = (
            header.get("Computer Name") or 
            comp_os.get("Computer Name") or 
            (original_filename.split("_")[0] if "_" in original_filename else "UNKNOWN-PC")
        ).strip()

        # Resolve IP address
        ip_addr = header.get("All IPv4 Addresses") or header.get("IP Address") or "N/A"
        if ip_addr == "1" and "All IPv4 Addresses" in header:
            ip_addr = header["All IPv4 Addresses"]

        report_date = header.get("Report Date", "N/A")
        report_file = header.get("Report File", original_filename or "N/A")

        asset = {
            "computer_name": comp_name,
            "ip_address": ip_addr,
            "all_ip_addresses": header.get("All IPv4 Addresses", ip_addr),
            "manufacturer": self._clean_str(comp_os.get("Manufacturer")),
            "model": self._clean_str(comp_os.get("Model")),
            "system_type": self._clean_str(comp_os.get("System Type")),
            "domain_workgroup": self._clean_str(comp_os.get("Domain / Workgroup")),
            "logged_user": self._clean_str(comp_os.get("Logged On User") or sections.get("current_user", {}).get("Current Logged User")),
            "report_date": report_date,
            "report_file": report_file,
            "original_filename": original_filename
        }

        # 2. Operating System
        os_info = {
            "name": self._clean_str(comp_os.get("Operating System")),
            "version": self._clean_str(comp_os.get("OS Version")),
            "build": self._clean_str(comp_os.get("OS Build")),
            "architecture": self._clean_str(comp_os.get("Architecture")),
            "serial": self._clean_str(comp_os.get("Windows Serial")),
            "install_date": self._clean_str(comp_os.get("Install Date")),
            "last_boot": self._clean_str(comp_os.get("Last Boot"))
        }

        # 3. CPU / Processor
        raw_cpu = sections.get("cpu", {}).get("items", [])
        cpus = []
        for c in raw_cpu:
            cpus.append({
                "name": self._clean_str(c.get("Name")),
                "manufacturer": self._clean_str(c.get("Manufacturer")),
                "model": self._clean_str(c.get("Model")),
                "processor_id": self._clean_str(c.get("Processor ID")),
                "serial_number": self._clean_str(c.get("Serial Number")),
                "socket": self._clean_str(c.get("Socket")),
                "current_speed_mhz": self._parse_int(c.get("Current Speed")),
                "maximum_speed_mhz": self._parse_int(c.get("Maximum Speed")),
                "cores": self._parse_int(c.get("Cores")),
                "threads": self._parse_int(c.get("Threads")),
                "architecture": self._clean_str(c.get("Architecture")),
                "status": self._clean_str(c.get("Status", "OK"))
            })

        # 4. RAM / Memory
        raw_ram = sections.get("ram", {}).get("items", [])
        ram_sticks = []
        total_ram_gb = self._parse_float(comp_os.get("Total Physical RAM"))
        stick_capacity_sum = 0.0

        for r in raw_ram:
            cap = self._parse_float(r.get("Capacity"))
            if cap:
                stick_capacity_sum += cap
            ram_sticks.append({
                "manufacturer": self._clean_str(r.get("Manufacturer")),
                "model": self._clean_str(r.get("Model / Part No")),
                "serial_number": self._clean_str(r.get("Serial Number")),
                "capacity_gb": cap,
                "speed_mhz": self._parse_int(r.get("Speed")),
                "configured_speed_mhz": self._parse_int(r.get("Configured Speed")),
                "device_locator": self._clean_str(r.get("Device Locator")),
                "bank_locator": self._clean_str(r.get("Bank Locator")),
                "memory_type": self._clean_str(r.get("Memory Type")),
                "form_factor": self._clean_str(r.get("Form Factor"))
            })

        if not total_ram_gb and stick_capacity_sum > 0:
            total_ram_gb = round(stick_capacity_sum, 2)

        # 5. Physical Storage and Health
        raw_disks = sections.get("physical_disks", {}).get("items", [])
        raw_health = sections.get("storage_health", {}).get("items", [])
        
        # Index storage health by serial number and model
        health_by_serial = {}
        health_by_model = {}
        for h in raw_health:
            s_num = self._clean_str(h.get("Serial Number"))
            if s_num and s_num != "N/A":
                health_by_serial[s_num.lower()] = h
            m_name = self._clean_str(h.get("Model") or h.get("Friendly Name"))
            if m_name and m_name != "N/A":
                health_by_model[m_name.lower()] = h

        storage = []
        seen_serials = set()

        for d in raw_disks:
            serial = self._clean_str(d.get("Serial Number"))
            model = self._clean_str(d.get("Model"))
            h_info = None
            if serial != "N/A" and serial.lower() in health_by_serial:
                h_info = health_by_serial[serial.lower()]
            elif model != "N/A" and model.lower() in health_by_model:
                h_info = health_by_model[model.lower()]

            media_type = "SSD" if h_info and "ssd" in str(h_info.get("Media Type", "")).lower() else self._clean_str(h_info.get("Media Type") if h_info else d.get("Media Type", "HDD"))
            health_status = self._clean_str(h_info.get("Health Status", "Healthy") if h_info else "Healthy")
            op_status = self._clean_str(h_info.get("Operational Status", "OK") if h_info else d.get("Status", "OK"))
            bus_type = self._clean_str(h_info.get("Bus Type") if h_info else d.get("Interface", "SATA"))
            size_val = self._parse_float(h_info.get("Size") if h_info else d.get("Size"))

            storage_item = {
                "device": self._clean_str(d.get("Device")),
                "model": model,
                "manufacturer": self._clean_str(d.get("Manufacturer")),
                "serial_number": serial,
                "media_type": media_type,
                "bus_type": bus_type,
                "size_gb": size_val,
                "health_status": health_status,
                "operational_status": op_status,
                "partitions_count": self._parse_int(d.get("Partitions"))
            }
            storage.append(storage_item)
            if serial != "N/A":
                seen_serials.add(serial.lower())

        # If physical_disks was empty, fallback to storage_health items
        if not storage and raw_health:
            for h in raw_health:
                storage.append({
                    "device": self._clean_str(h.get("Friendly Name")),
                    "model": self._clean_str(h.get("Model") or h.get("Friendly Name")),
                    "manufacturer": self._clean_str(h.get("Manufacturer")),
                    "serial_number": self._clean_str(h.get("Serial Number")),
                    "media_type": self._clean_str(h.get("Media Type", "SSD")),
                    "bus_type": self._clean_str(h.get("Bus Type", "SATA")),
                    "size_gb": self._parse_float(h.get("Size")),
                    "health_status": self._clean_str(h.get("Health Status", "Healthy")),
                    "operational_status": self._clean_str(h.get("Operational Status", "OK")),
                    "partitions_count": None
                })

        # 6. Drive / Partition Space
        raw_drives = sections.get("drive_space", {}).get("items", [])
        drives = []
        for drv in raw_drives:
            letter = self._clean_str(drv.get("Drive"))
            total_sz = self._parse_float(drv.get("Total Size"))
            used_sz = self._parse_float(drv.get("Used Space"))
            free_sz = self._parse_float(drv.get("Free Space"))
            free_pct = self._parse_float(drv.get("Free Percentage"))

            # Calculate free percentage if missing
            if free_pct is None and total_sz and free_sz:
                free_pct = round((free_sz / total_sz) * 100.0, 2)

            # Capacity status classification
            drv_status = "NORMAL"
            if free_pct is not None:
                if free_pct <= LOW_STORAGE_CRITICAL_PERCENT:
                    drv_status = "CRITICAL"
                elif free_pct <= LOW_STORAGE_WARNING_PERCENT:
                    drv_status = "WARNING"

            drives.append({
                "drive_letter": letter,
                "volume_name": self._clean_str(drv.get("Volume Name")),
                "file_system": self._clean_str(drv.get("File System")),
                "total_size_gb": total_sz,
                "used_space_gb": used_sz,
                "free_space_gb": free_sz,
                "free_percentage": free_pct,
                "status": drv_status
            })

        # 7. GPU
        raw_gpus = sections.get("gpu", {}).get("items", [])
        gpus = []
        for g in raw_gpus:
            gpus.append({
                "name": self._clean_str(g.get("Name")),
                "manufacturer": self._clean_str(g.get("Manufacturer")),
                "driver_version": self._clean_str(g.get("Driver Version")),
                "video_memory": self._clean_str(g.get("Video Memory")),
                "video_processor": self._clean_str(g.get("Video Processor")),
                "resolution": self._clean_str(g.get("Resolution")),
                "refresh_rate": self._clean_str(g.get("Refresh Rate"))
            })

        # 8. Monitors
        raw_monitors = sections.get("monitors", {}).get("items", [])
        monitors = []
        for m in raw_monitors:
            monitors.append({
                "manufacturer": self._clean_str(m.get("Manufacturer")),
                "model": self._clean_str(m.get("Model")),
                "product_code": self._clean_str(m.get("Product Code")),
                "serial_number": self._clean_str(m.get("Serial Number"))
            })

        # 9. Keyboards
        raw_kb = sections.get("keyboards", {}).get("items", [])
        keyboards = []
        for k in raw_kb:
            keyboards.append({
                "name": self._clean_str(k.get("Name")),
                "description": self._clean_str(k.get("Description")),
                "manufacturer": self._clean_str(k.get("Manufacturer")),
                "device_id": self._clean_str(k.get("Device ID")),
                "status": self._clean_str(k.get("Status", "OK"))
            })

        # 10. Mice
        raw_mice = sections.get("mice", {}).get("items", [])
        mice = []
        for m in raw_mice:
            mice.append({
                "name": self._clean_str(m.get("Name")),
                "description": self._clean_str(m.get("Description")),
                "manufacturer": self._clean_str(m.get("Manufacturer")),
                "device_id": self._clean_str(m.get("Device ID")),
                "hardware_type": self._clean_str(m.get("Hardware Type")),
                "status": self._clean_str(m.get("Status", "OK"))
            })

        # 11. USB Devices
        raw_usb = sections.get("usb_devices", {}).get("items", [])
        usb_devices = []
        for u in raw_usb:
            usb_devices.append({
                "name": self._clean_str(u.get("Name")),
                "manufacturer": self._clean_str(u.get("Manufacturer")),
                "device_id": self._clean_str(u.get("Device ID")),
                "pnp_device_id": self._clean_str(u.get("PNP Device ID") or u.get("Device ID")),
                "status": self._clean_str(u.get("Status", "OK"))
            })

        # 12. Network Adapters
        raw_net = sections.get("network_adapters", {}).get("items", [])
        network_adapters = []
        for n in raw_net:
            network_adapters.append({
                "name": self._clean_str(n.get("Name")),
                "manufacturer": self._clean_str(n.get("Manufacturer")),
                "mac_address": self._clean_str(n.get("MAC Address")),
                "adapter_type": self._clean_str(n.get("Adapter Type")),
                "speed": self._clean_str(n.get("Speed")),
                "device_id": self._clean_str(n.get("Device ID")),
                "status": self._clean_str(n.get("Status", "OK"))
            })

        # 13. Motherboard
        mb = sections.get("motherboard", {})
        motherboard = {
            "manufacturer": self._clean_str(mb.get("Manufacturer")),
            "model": self._clean_str(mb.get("Product / Model") or mb.get("Model")),
            "version": self._clean_str(mb.get("Version")),
            "serial_number": self._clean_str(mb.get("Serial Number")),
            "part_number": self._clean_str(mb.get("Part Number")),
            "status": self._clean_str(mb.get("Status", "OK"))
        }

        # 14. BIOS
        bios_sec = sections.get("bios", {})
        bios = {
            "manufacturer": self._clean_str(bios_sec.get("Manufacturer")),
            "bios_version": self._clean_str(bios_sec.get("BIOS Version")),
            "bios_version_2": self._clean_str(bios_sec.get("BIOS Version 2")),
            "serial_number": self._clean_str(bios_sec.get("BIOS Serial Number") or bios_sec.get("Serial Number")),
            "release_date": self._clean_str(bios_sec.get("Release Date")),
            "smbios_major": self._clean_str(bios_sec.get("SMBIOS Major")),
            "smbios_minor": self._clean_str(bios_sec.get("SMBIOS Minor"))
        }

        # 15. Installed Software (Preserved, but segregated from main hardware view)
        raw_sw = sections.get("installed_software", {}).get("items", [])
        software_list = []
        for s in raw_sw:
            software_list.append({
                "name": self._clean_str(s.get("Name")),
                "version": self._clean_str(s.get("Version")),
                "publisher": self._clean_str(s.get("Publisher")),
                "install_date": self._clean_str(s.get("Install Date")),
                "install_location": self._clean_str(s.get("Install Location")),
                "architecture": self._clean_str(s.get("Architecture"))
            })

        normalized = {
            "asset": asset,
            "os": os_info,
            "cpu": cpus,
            "ram": ram_sticks,
            "total_ram_gb": total_ram_gb,
            "storage": storage,
            "drives": drives,
            "gpu": gpus,
            "monitors": monitors,
            "keyboards": keyboards,
            "mice": mice,
            "usb_devices": usb_devices,
            "network_adapters": network_adapters,
            "motherboard": motherboard,
            "bios": bios,
            "software_count": len(software_list),
            "installed_software": software_list
        }

        parser_logger.info(
            f"Normalized data for '{comp_name}': {len(cpus)} CPUs, {len(ram_sticks)} RAM sticks, "
            f"{len(storage)} Disks, {len(drives)} Drives, {len(gpus)} GPUs, {len(monitors)} Monitors, "
            f"{len(usb_devices)} USB devices, {len(software_list)} Installed Software."
        )

        return normalized
