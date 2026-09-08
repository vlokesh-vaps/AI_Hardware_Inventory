"""
Inventory Repository Service.
Manages snapshot persistence, asset querying, hardware change history, and KPI aggregation.
Designed with a repository pattern to allow future migration to PostgreSQL.
"""
import json
import re
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import (
    RAW_DIR,
    SNAPSHOTS_DIR,
    NORMALIZED_DIR,
    CHANGES_DIR,
    app_logger,
    error_logger,
    change_logger
)
from parser.txt_parser import TxtParser
from parser.normalizer import DataNormalizer
from parser.change_detector import HardwareChangeDetector
from services.health_service import HealthService

class InventoryService:
    """Repository service providing isolated data access and business logic for hardware inventory."""

    def __init__(self):
        self.parser = TxtParser()
        self.normalizer = DataNormalizer()
        self.change_detector = HardwareChangeDetector()
        self.health_service = HealthService()

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Replaces characters that are illegal in file names."""
        return re.sub(r'[:/\\?*|"<>]', '_', name).strip()

    def process_report_file(self, content_or_path: Any, filename: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Orchestrates reading, parsing, normalizing, evaluating health, and saving a health check report.
        Returns: (success: bool, message: str, asset_data: Optional[Dict])
        """
        try:
            # 1. Parse raw content
            raw_data = self.parser.parse(content_or_path)

            # 2. Normalize
            normalized_data = self.normalizer.normalize(raw_data, original_filename=filename)

            # 3. Calculate health
            health = self.health_service.evaluate_health(normalized_data)
            normalized_data["health"] = health

            # 4. Extract raw text for storage
            raw_text = ""
            if isinstance(content_or_path, (str, Path)) and Path(str(content_or_path)).is_file():
                with open(content_or_path, "r", encoding="utf-8", errors="replace") as f:
                    raw_text = f.read()
            elif isinstance(content_or_path, str):
                raw_text = content_or_path

            # 5. Save snapshot & detect changes
            success, msg, changes = self.save_snapshot(normalized_data, raw_text, filename)
            if not success:
                return False, msg, normalized_data

            return True, f"Successfully processed report for {normalized_data['asset']['computer_name']}. {len(changes)} changes detected.", normalized_data

        except Exception as e:
            err_msg = f"Error processing file '{filename}': {str(e)}"
            error_logger.exception(err_msg)
            return False, err_msg, None

    def save_snapshot(
        self,
        normalized_data: Dict[str, Any],
        raw_content: str,
        filename: str
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Saves snapshot JSON, preserves raw text, compares with previous snapshot, and tracks changes.
        """
        comp_name = normalized_data.get("asset", {}).get("computer_name", "UNKNOWN-PC")
        report_date = normalized_data.get("asset", {}).get("report_date", "N/A")

        if not comp_name or comp_name == "N/A":
            return False, "Validation Error: Missing Computer Name in report.", []

        sanitized_comp = self._sanitize_filename(comp_name)
        sanitized_date = self._sanitize_filename(report_date if report_date != "N/A" else Path(filename).stem)

        comp_snapshots_dir = SNAPSHOTS_DIR / sanitized_comp
        comp_snapshots_dir.mkdir(parents=True, exist_ok=True)

        snapshot_file = comp_snapshots_dir / f"{sanitized_date}.json"

        # Check duplicate snapshot policy
        if snapshot_file.exists():
            app_logger.warning(f"Duplicate snapshot detected for {comp_name} at {report_date}.")
            return False, f"Duplicate snapshot: Report for {comp_name} on {report_date} has already been imported.", []

        # Find previous snapshot before saving this one
        prev_snapshot = self.get_latest_snapshot(comp_name)

        # Detect changes against previous snapshot
        changes: List[Dict[str, Any]] = []
        if prev_snapshot is not None:
            changes = self.change_detector.detect_changes(prev_snapshot, normalized_data)
            if changes:
                self._save_changes(comp_name, changes)

        # Save snapshot JSON
        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(normalized_data, f, indent=2)

        # Save raw TXT file copy
        if raw_content:
            raw_target = RAW_DIR / f"{sanitized_comp}_{sanitized_date}.txt"
            with open(raw_target, "w", encoding="utf-8") as f:
                f.write(raw_content)

        # Update latest normalized record
        normalized_file = NORMALIZED_DIR / f"{sanitized_comp}.json"
        with open(normalized_file, "w", encoding="utf-8") as f:
            json.dump(normalized_data, f, indent=2)

        app_logger.info(f"Snapshot saved for {comp_name} at {snapshot_file}")
        return True, "Snapshot saved successfully.", changes

    def _save_changes(self, computer_name: str, new_changes: List[Dict[str, Any]]) -> None:
        """Appends newly detected changes to PC-specific and global changes log."""
        sanitized_comp = self._sanitize_filename(computer_name)
        comp_changes_file = CHANGES_DIR / f"{sanitized_comp}_changes.json"
        global_changes_file = CHANGES_DIR / "all_changes.json"

        # Load existing PC changes
        comp_changes = []
        if comp_changes_file.exists():
            try:
                with open(comp_changes_file, "r", encoding="utf-8") as f:
                    comp_changes = json.load(f)
            except Exception:
                comp_changes = []

        comp_changes = new_changes + comp_changes
        with open(comp_changes_file, "w", encoding="utf-8") as f:
            json.dump(comp_changes, f, indent=2)

        # Load existing Global changes
        global_changes = []
        if global_changes_file.exists():
            try:
                with open(global_changes_file, "r", encoding="utf-8") as f:
                    global_changes = json.load(f)
            except Exception:
                global_changes = []

        global_changes = new_changes + global_changes
        with open(global_changes_file, "w", encoding="utf-8") as f:
            json.dump(global_changes, f, indent=2)

        change_logger.info(f"Persisted {len(new_changes)} changes for {computer_name}")

    def get_latest_snapshot(self, computer_name: str) -> Optional[Dict[str, Any]]:
        """Returns the latest normalized snapshot for a computer."""
        sanitized_comp = self._sanitize_filename(computer_name)
        norm_file = NORMALIZED_DIR / f"{sanitized_comp}.json"
        if norm_file.exists():
            try:
                with open(norm_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                error_logger.error(f"Failed to read normalized file {norm_file}: {e}")

        # Fallback to scanning snapshots directory
        comp_snapshots_dir = SNAPSHOTS_DIR / sanitized_comp
        if comp_snapshots_dir.exists():
            files = sorted(comp_snapshots_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                try:
                    with open(files[0], "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    error_logger.error(f"Failed to read snapshot {files[0]}: {e}")
        return None

    def get_snapshot_history(self, computer_name: str) -> List[Dict[str, Any]]:
        """Returns all snapshots for a computer ordered by report date descending."""
        sanitized_comp = self._sanitize_filename(computer_name)
        comp_snapshots_dir = SNAPSHOTS_DIR / sanitized_comp
        if not comp_snapshots_dir.exists():
            return []

        history = []
        for file_path in comp_snapshots_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    history.append({
                        "filename": file_path.name,
                        "report_date": data.get("asset", {}).get("report_date", file_path.stem),
                        "total_ram_gb": data.get("total_ram_gb"),
                        "storage_count": len(data.get("storage", [])),
                        "overall_health": data.get("health", {}).get("overall", "UNKNOWN")
                    })
            except Exception as e:
                error_logger.warning(f"Could not read historical snapshot {file_path}: {e}")

        history.sort(key=lambda x: str(x.get("report_date", "")), reverse=True)
        return history

    def get_assets(self) -> List[Dict[str, Any]]:
        """Returns a list of all active computer assets with their latest specs and health."""
        assets = []
        for norm_file in NORMALIZED_DIR.glob("*.json"):
            try:
                with open(norm_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Compute or refresh health
                    health = data.get("health")
                    if not health:
                        health = self.health_service.evaluate_health(data)
                        data["health"] = health

                    assets.append(data)
            except Exception as e:
                error_logger.error(f"Error loading asset from {norm_file}: {e}")

        assets.sort(key=lambda a: a.get("asset", {}).get("computer_name", "").lower())
        return assets

    def get_changes(self, filters: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Returns hardware changes, optionally filtered by computer, component, change_type, date."""
        global_changes_file = CHANGES_DIR / "all_changes.json"
        if not global_changes_file.exists():
            return []

        try:
            with open(global_changes_file, "r", encoding="utf-8") as f:
                changes = json.load(f)
        except Exception as e:
            error_logger.error(f"Error reading changes log: {e}")
            return []

        if not filters:
            return changes

        filtered = []
        for c in changes:
            if filters.get("computer_name") and filters["computer_name"].lower() not in c.get("computer_name", "").lower():
                continue
            if filters.get("component_type") and filters["component_type"].lower() != c.get("component_type", "").lower():
                continue
            if filters.get("change_type") and filters["change_type"].upper() != c.get("change_type", "").upper():
                continue
            if filters.get("date") and filters["date"] not in c.get("date", ""):
                continue
            filtered.append(c)

        return filtered

    def get_storage_alerts(self) -> List[Dict[str, Any]]:
        """Gathers all drive partitions across all computers that have capacity warnings or critical status."""
        alerts = []
        for asset in self.get_assets():
            comp_name = asset.get("asset", {}).get("computer_name", "N/A")
            ip_addr = asset.get("asset", {}).get("ip_address", "N/A")
            for drv in asset.get("drives", []):
                status = drv.get("status", "NORMAL")
                if status in ("WARNING", "CRITICAL"):
                    alerts.append({
                        "computer_name": comp_name,
                        "ip_address": ip_addr,
                        "drive_letter": drv.get("drive_letter"),
                        "volume_name": drv.get("volume_name"),
                        "file_system": drv.get("file_system"),
                        "total_size_gb": drv.get("total_size_gb"),
                        "used_space_gb": drv.get("used_space_gb"),
                        "free_space_gb": drv.get("free_space_gb"),
                        "free_percentage": drv.get("free_percentage"),
                        "status": status
                    })
        return alerts

    def get_upgrade_recommendations(self) -> List[Dict[str, Any]]:
        """Aggregates all upgrade recommendations across all assets."""
        recommendations = []
        for asset in self.get_assets():
            comp_name = asset.get("asset", {}).get("computer_name", "N/A")
            ip_addr = asset.get("asset", {}).get("ip_address", "N/A")
            model = asset.get("asset", {}).get("model", "N/A")
            health = asset.get("health", {})
            for rec in health.get("recommendations", []):
                rec_dict = rec if isinstance(rec, dict) else rec.to_dict()
                rec_dict["computer_name"] = comp_name
                rec_dict["ip_address"] = ip_addr
                rec_dict["model"] = model
                recommendations.append(rec_dict)
        return recommendations

    def get_kpis(self) -> Dict[str, int]:
        """Calculates dashboard summary metrics."""
        assets = self.get_assets()
        total_assets = len(assets)
        healthy = 0
        warning = 0
        critical = 0
        upgrade_count = 0

        for a in assets:
            overall = a.get("health", {}).get("overall", "UNKNOWN")
            if overall == "HEALTHY":
                healthy += 1
            elif overall == "WARNING":
                warning += 1
            elif overall == "CRITICAL":
                critical += 1
            upgrade_count += a.get("health", {}).get("upgrade_required_count", 0)

        changes = self.get_changes()
        storage_alerts = len(self.get_storage_alerts())

        return {
            "total_assets": total_assets,
            "healthy": healthy,
            "warning": warning,
            "critical": critical,
            "hardware_changes": len(changes),
            "storage_alerts": storage_alerts,
            "upgrade_required": upgrade_count
        }
