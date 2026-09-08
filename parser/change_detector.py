"""
Hardware Change Detector for tracking modifications across snapshots of a computer.
Uses stable identifiers to detect ADDED, REMOVED, and CHANGED components.
"""
from typing import Dict, Any, List, Tuple
from config import change_logger
from models.schemas import HardwareChange

class HardwareChangeDetector:
    """Detects hardware modifications between two snapshots of the same machine."""

    @staticmethod
    def _clean_id(val: Any) -> str:
        if not val or str(val).strip() in ("N/A", "None", ""):
            return ""
        return str(val).strip().lower()

    def detect_changes(self, prev_snapshot: Dict[str, Any], curr_snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Compares previous snapshot with current snapshot and returns a list of HardwareChange dicts.
        """
        changes: List[HardwareChange] = []
        comp_name = curr_snapshot.get("asset", {}).get("computer_name", "UNKNOWN-PC")
        report_date = curr_snapshot.get("asset", {}).get("report_date", "N/A")

        change_logger.info(f"Comparing snapshots for {comp_name}: previous vs current ({report_date})")

        # 1. RAM Modules
        self._compare_list(
            prev_items=prev_snapshot.get("ram", []),
            curr_items=curr_snapshot.get("ram", []),
            comp_name=comp_name,
            report_date=report_date,
            component_type="RAM",
            get_id=lambda r: self._clean_id(r.get("serial_number")) or self._clean_id(r.get("device_locator")),
            format_item=lambda r: f"{r.get('capacity_gb', 'N/A')} GB {r.get('model', '')} ({r.get('device_locator', 'N/A')}, S/N: {r.get('serial_number', 'N/A')})",
            check_change=lambda p, c: (
                p.get("capacity_gb") != c.get("capacity_gb") or 
                p.get("model") != c.get("model"),
                f"Capacity/Model changed from {p.get('capacity_gb')}GB to {c.get('capacity_gb')}GB"
            ),
            collector=changes
        )

        # 2. Storage Disks
        self._compare_list(
            prev_items=prev_snapshot.get("storage", []),
            curr_items=curr_snapshot.get("storage", []),
            comp_name=comp_name,
            report_date=report_date,
            component_type="Storage",
            get_id=lambda s: self._clean_id(s.get("serial_number")) or self._clean_id(s.get("device")),
            format_item=lambda s: f"{s.get('model', 'Disk')} ({s.get('size_gb', 'N/A')} GB, {s.get('media_type', 'N/A')}, S/N: {s.get('serial_number', 'N/A')})",
            check_change=lambda p, c: (
                p.get("model") != c.get("model") or p.get("size_gb") != c.get("size_gb"),
                f"Disk replaced or resized: {p.get('model')} ({p.get('size_gb')}GB) -> {c.get('model')} ({c.get('size_gb')}GB)"
            ),
            collector=changes
        )

        # 3. Monitors
        self._compare_list(
            prev_items=prev_snapshot.get("monitors", []),
            curr_items=curr_snapshot.get("monitors", []),
            comp_name=comp_name,
            report_date=report_date,
            component_type="Monitor",
            get_id=lambda m: self._clean_id(m.get("serial_number")) or f"{self._clean_id(m.get('model'))}_{self._clean_id(m.get('product_code'))}",
            format_item=lambda m: f"{m.get('manufacturer', '')} {m.get('model', 'Monitor')} (Code: {m.get('product_code', 'N/A')}, S/N: {m.get('serial_number', 'N/A')})",
            check_change=lambda p, c: (
                p.get("model") != c.get("model") or p.get("product_code") != c.get("product_code"),
                f"Monitor changed from {p.get('model')} to {c.get('model')}"
            ),
            collector=changes
        )

        # 4. GPU / Graphics
        self._compare_list(
            prev_items=prev_snapshot.get("gpu", []),
            curr_items=curr_snapshot.get("gpu", []),
            comp_name=comp_name,
            report_date=report_date,
            component_type="GPU",
            get_id=lambda g: f"{self._clean_id(g.get('name'))}_{self._clean_id(g.get('manufacturer'))}",
            format_item=lambda g: f"{g.get('name', 'GPU')} ({g.get('video_memory', 'N/A')})",
            check_change=lambda p, c: (
                p.get("name") != c.get("name") or p.get("video_memory") != c.get("video_memory"),
                f"GPU hardware changed: {p.get('name')} -> {c.get('name')}"
            ),
            collector=changes
        )

        # 5. Keyboards
        self._compare_list(
            prev_items=prev_snapshot.get("keyboards", []),
            curr_items=curr_snapshot.get("keyboards", []),
            comp_name=comp_name,
            report_date=report_date,
            component_type="Keyboard",
            get_id=lambda k: self._clean_id(k.get("device_id")) or self._clean_id(k.get("name")),
            format_item=lambda k: f"{k.get('name', 'Keyboard')} ({k.get('description', 'N/A')})",
            check_change=lambda p, c: (
                p.get("name") != c.get("name") or p.get("description") != c.get("description"),
                f"Keyboard changed: {p.get('name')} -> {c.get('name')}"
            ),
            collector=changes
        )

        # 6. Mice
        self._compare_list(
            prev_items=prev_snapshot.get("mice", []),
            curr_items=curr_snapshot.get("mice", []),
            comp_name=comp_name,
            report_date=report_date,
            component_type="Mouse",
            get_id=lambda m: self._clean_id(m.get("device_id")) or self._clean_id(m.get("name")),
            format_item=lambda m: f"{m.get('name', 'Mouse')} ({m.get('description', 'N/A')})",
            check_change=lambda p, c: (
                p.get("name") != c.get("name"),
                f"Mouse changed: {p.get('name')} -> {c.get('name')}"
            ),
            collector=changes
        )

        # 7. USB Devices
        self._compare_list(
            prev_items=prev_snapshot.get("usb_devices", []),
            curr_items=curr_snapshot.get("usb_devices", []),
            comp_name=comp_name,
            report_date=report_date,
            component_type="USB Device",
            get_id=lambda u: self._clean_id(u.get("pnp_device_id")) or self._clean_id(u.get("device_id")),
            format_item=lambda u: f"{u.get('name', 'USB Device')} ({u.get('manufacturer', 'N/A')})",
            check_change=lambda p, c: (
                p.get("name") != c.get("name"),
                f"USB device changed: {p.get('name')} -> {c.get('name')}"
            ),
            collector=changes
        )

        # 8. Network Adapters
        self._compare_list(
            prev_items=prev_snapshot.get("network_adapters", []),
            curr_items=curr_snapshot.get("network_adapters", []),
            comp_name=comp_name,
            report_date=report_date,
            component_type="Network Adapter",
            get_id=lambda n: self._clean_id(n.get("mac_address")) or self._clean_id(n.get("name")),
            format_item=lambda n: f"{n.get('name', 'Adapter')} (MAC: {n.get('mac_address', 'N/A')})",
            check_change=lambda p, c: (
                p.get("name") != c.get("name") or p.get("speed") != c.get("speed"),
                f"Network adapter modified: {p.get('name')} -> {c.get('name')}"
            ),
            collector=changes
        )

        # 9. CPU
        self._compare_list(
            prev_items=prev_snapshot.get("cpu", []),
            curr_items=curr_snapshot.get("cpu", []),
            comp_name=comp_name,
            report_date=report_date,
            component_type="CPU",
            get_id=lambda c: self._clean_id(c.get("processor_id")) or self._clean_id(c.get("name")),
            format_item=lambda c: f"{c.get('name', 'CPU')} ({c.get('cores', 'N/A')} cores, {c.get('threads', 'N/A')} threads)",
            check_change=lambda p, c: (
                p.get("name") != c.get("name") or p.get("cores") != c.get("cores"),
                f"CPU changed: {p.get('name')} ({p.get('cores')} cores) -> {c.get('name')} ({c.get('cores')} cores)"
            ),
            collector=changes
        )

        change_logger.info(f"Detected {len(changes)} changes for {comp_name}")
        return [c.to_dict() for c in changes]

    def _compare_list(
        self,
        prev_items: List[Dict[str, Any]],
        curr_items: List[Dict[str, Any]],
        comp_name: str,
        report_date: str,
        component_type: str,
        get_id,
        format_item,
        check_change,
        collector: List[HardwareChange]
    ) -> None:
        """Helper to match lists of items by stable ID and detect ADDED, REMOVED, CHANGED."""
        prev_map = {}
        for idx, item in enumerate(prev_items):
            item_id = get_id(item) or f"_idx_{idx}"
            prev_map[item_id] = item

        curr_map = {}
        for idx, item in enumerate(curr_items):
            item_id = get_id(item) or f"_idx_{idx}"
            curr_map[item_id] = item

        # Detect ADDED
        for item_id, curr_item in curr_map.items():
            if item_id not in prev_map:
                collector.append(HardwareChange(
                    date=report_date,
                    computer_name=comp_name,
                    component_type=component_type,
                    change_type="ADDED",
                    description=f"Added {component_type}: {format_item(curr_item)}",
                    previous_value="N/A",
                    current_value=format_item(curr_item)
                ))

        # Detect REMOVED
        for item_id, prev_item in prev_map.items():
            if item_id not in curr_map:
                collector.append(HardwareChange(
                    date=report_date,
                    computer_name=comp_name,
                    component_type=component_type,
                    change_type="REMOVED",
                    description=f"Removed {component_type}: {format_item(prev_item)}",
                    previous_value=format_item(prev_item),
                    current_value="N/A"
                ))

        # Detect CHANGED
        for item_id in prev_map:
            if item_id in curr_map:
                p_item = prev_map[item_id]
                c_item = curr_map[item_id]
                is_changed, desc = check_change(p_item, c_item)
                if is_changed:
                    collector.append(HardwareChange(
                        date=report_date,
                        computer_name=comp_name,
                        component_type=component_type,
                        change_type="CHANGED",
                        description=f"Changed {component_type}: {desc}",
                        previous_value=format_item(p_item),
                        current_value=format_item(c_item)
                    ))
