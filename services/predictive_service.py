"""
Predictive Analysis & Risk Engine Service.
Evaluates multi-factor hardware failure risks, projects storage exhaustion runways,
and aggregates historical health status over time for predictive fleet maintenance.
"""
from datetime import datetime, timedelta
import math
from pathlib import Path
from typing import Dict, Any, List, Optional
from dateutil import parser as date_parser

from config import (
    SNAPSHOTS_DIR,
    LOW_STORAGE_WARNING_PERCENT,
    LOW_STORAGE_CRITICAL_PERCENT,
    RECOMMENDED_MIN_RAM_GB,
    RECOMMENDED_MIN_CPU_CORES,
    RISK_THRESHOLD_CRITICAL,
    RISK_THRESHOLD_HIGH,
    RISK_THRESHOLD_MODERATE,
    predictive_logger,
    error_logger
)
from services.inventory_service import InventoryService
from services.monitoring_service import MonitoringService


class PredictiveService:
    """
    Predictive engine assessing hardware failure likelihood, storage depletion runway,
    and historical health trends across the enterprise fleet.
    """

    def __init__(
        self,
        inventory_service: Optional[InventoryService] = None,
        monitoring_service: Optional[MonitoringService] = None
    ):
        self.inventory_service = inventory_service or InventoryService()
        self.monitoring_service = monitoring_service or MonitoringService()

    def assess_system_risk(
        self,
        asset_data: Dict[str, Any],
        live_telemetry: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Calculates a composite 0-100 risk score for an asset across 5 vectors:
        1. Storage partition exhaustion & runway
        2. Physical disk & hardware controller health
        3. Hardware specification bottlenecks
        4. Recent hardware volatility / component changes
        5. Live telemetry status and resource saturation
        """
        comp_name = asset_data.get("asset", {}).get("computer_name", "UNKNOWN-PC")
        ip_addr = asset_data.get("asset", {}).get("ip_address", "N/A")
        model = asset_data.get("asset", {}).get("model", "N/A")
        health = asset_data.get("health", {})

        raw_score = 0
        risk_factors: List[Dict[str, Any]] = []
        failure_vectors: List[str] = []

        # -------------------------------------------------------------
        # Vector 1: Storage Partition Exhaustion & Runway (Weight: up to 35)
        # -------------------------------------------------------------
        critical_drives = []
        warning_drives = []
        for drv in asset_data.get("drives", []):
            letter = drv.get("drive_letter", "Drive")
            free_pct = drv.get("free_percentage")
            free_gb = drv.get("free_space_gb", 0)

            if free_pct is not None:
                if free_pct <= LOW_STORAGE_CRITICAL_PERCENT:
                    critical_drives.append((letter, free_pct, free_gb))
                elif free_pct <= LOW_STORAGE_WARNING_PERCENT:
                    warning_drives.append((letter, free_pct, free_gb))

        if critical_drives:
            score_add = 35
            raw_score += score_add
            failure_vectors.append("Storage Exhaustion")
            for letter, free_pct, free_gb in critical_drives:
                risk_factors.append({
                    "category": "Storage",
                    "severity": "CRITICAL",
                    "impact_points": score_add,
                    "description": f"Drive {letter} is in critical capacity state: {free_pct}% free ({free_gb} GB remaining)."
                })
        elif warning_drives:
            score_add = 20
            raw_score += score_add
            failure_vectors.append("Storage Capacity Warning")
            for letter, free_pct, free_gb in warning_drives:
                risk_factors.append({
                    "category": "Storage",
                    "severity": "WARNING",
                    "impact_points": score_add,
                    "description": f"Drive {letter} is approaching capacity: {free_pct}% free ({free_gb} GB remaining)."
                })

        # -------------------------------------------------------------
        # Vector 2: Physical Storage & Hardware Health (Weight: up to 35)
        # -------------------------------------------------------------
        disk_issues = []
        for disk in asset_data.get("storage", []):
            h_stat = str(disk.get("health_status", "")).strip().lower()
            op_stat = str(disk.get("operational_status", "")).strip().lower()
            model_disk = disk.get("model", "Physical Disk")
            serial = disk.get("serial_number", "N/A")

            if h_stat in ("unhealthy", "failing", "error", "bad") or op_stat in ("error", "failed", "degraded"):
                disk_issues.append((model_disk, serial, disk.get("health_status"), disk.get("operational_status"), "CRITICAL"))
            elif h_stat in ("warning", "caution") or op_stat in ("warning", "caution"):
                disk_issues.append((model_disk, serial, disk.get("health_status"), disk.get("operational_status"), "WARNING"))

        if disk_issues:
            crit_disks = [d for d in disk_issues if d[4] == "CRITICAL"]
            if crit_disks:
                raw_score += 35
                failure_vectors.append("Physical Drive Degradation")
                for m_d, ser, hs, ops, _ in crit_disks:
                    risk_factors.append({
                        "category": "Hardware Health",
                        "severity": "CRITICAL",
                        "impact_points": 35,
                        "description": f"Physical disk '{m_d}' (S/N: {ser}) flagged failing health: {hs} / {ops}."
                    })
            else:
                raw_score += 20
                failure_vectors.append("Drive Health Warning")
                for m_d, ser, hs, ops, _ in disk_issues:
                    risk_factors.append({
                        "category": "Hardware Health",
                        "severity": "WARNING",
                        "impact_points": 20,
                        "description": f"Physical disk '{m_d}' (S/N: {ser}) flagged cautionary health: {hs}."
                    })

        # Motherboard & CPU integrity
        mb_stat = str(asset_data.get("motherboard", {}).get("status", "")).strip().lower()
        if mb_stat in ("error", "failed", "degraded"):
            raw_score += 25
            failure_vectors.append("Motherboard Fault")
            risk_factors.append({
                "category": "Motherboard",
                "severity": "CRITICAL",
                "impact_points": 25,
                "description": f"Motherboard reported degraded status: '{asset_data.get('motherboard', {}).get('status')}'."
            })

        for cpu in asset_data.get("cpu", []):
            c_stat = str(cpu.get("status", "")).strip().lower()
            if c_stat in ("error", "failed", "degraded"):
                raw_score += 25
                failure_vectors.append("CPU Degradation")
                risk_factors.append({
                    "category": "CPU",
                    "severity": "CRITICAL",
                    "impact_points": 25,
                    "description": f"CPU '{cpu.get('name', 'CPU')}' reported abnormal status: '{cpu.get('status')}'."
                })

        # -------------------------------------------------------------
        # Vector 3: Resource Constraints & Age/Spec Bottlenecks (Weight: up to 25)
        # -------------------------------------------------------------
        total_ram = asset_data.get("total_ram_gb")
        if total_ram is not None:
            if total_ram < 8.0:
                raw_score += 20
                failure_vectors.append("Severe RAM Bottleneck")
                risk_factors.append({
                    "category": "Specification",
                    "severity": "HIGH",
                    "impact_points": 20,
                    "description": f"Sub-standard system memory: only {total_ram} GB installed (Enterprise minimum 16 GB)."
                })
            elif total_ram < RECOMMENDED_MIN_RAM_GB:
                raw_score += 10
                risk_factors.append({
                    "category": "Specification",
                    "severity": "MODERATE",
                    "impact_points": 10,
                    "description": f"System memory ({total_ram} GB) is below 16 GB enterprise baseline."
                })

        cpus = asset_data.get("cpu", [])
        if cpus:
            cores = cpus[0].get("cores")
            if cores and cores < RECOMMENDED_MIN_CPU_CORES:
                raw_score += 10
                risk_factors.append({
                    "category": "Specification",
                    "severity": "MODERATE",
                    "impact_points": 10,
                    "description": f"CPU has only {cores} core(s), below enterprise baseline of {RECOMMENDED_MIN_CPU_CORES}."
                })

        # -------------------------------------------------------------
        # Vector 4: Hardware Volatility & Recent Changes (Weight: up to 15)
        # -------------------------------------------------------------
        try:
            recent_changes = self.inventory_service.get_changes({"computer_name": comp_name})
            if recent_changes:
                removed_changes = [c for c in recent_changes if c.get("change_type") == "REMOVED"]
                if removed_changes:
                    raw_score += 15
                    failure_vectors.append("Component Removal")
                    risk_factors.append({
                        "category": "Hardware Volatility",
                        "severity": "HIGH",
                        "impact_points": 15,
                        "description": f"{len(removed_changes)} hardware component(s) recently removed or unseated."
                    })
                elif len(recent_changes) >= 3:
                    raw_score += 10
                    risk_factors.append({
                        "category": "Hardware Volatility",
                        "severity": "MODERATE",
                        "impact_points": 10,
                        "description": f"Frequent hardware modifications: {len(recent_changes)} component modifications recorded."
                    })
        except Exception as e:
            predictive_logger.debug(f"Could not load changes for risk calculation on {comp_name}: {e}")

        # -------------------------------------------------------------
        # Vector 5: Live Telemetry Saturation (Weight: up to 25)
        # -------------------------------------------------------------
        if live_telemetry:
            if not live_telemetry.get("online", True):
                raw_score += 20
                failure_vectors.append("Offline Telemetry")
                risk_factors.append({
                    "category": "Live Telemetry",
                    "severity": "HIGH",
                    "impact_points": 20,
                    "description": "System endpoint is offline or unresponsive to Prometheus monitoring."
                })
            else:
                metrics = live_telemetry.get("metrics", {})
                cpu_p = metrics.get("cpu_percent")
                mem_p = metrics.get("memory_percent")
                if cpu_p is not None and cpu_p >= 90.0:
                    raw_score += 15
                    failure_vectors.append("Sustained High CPU")
                    risk_factors.append({
                        "category": "Live Telemetry",
                        "severity": "HIGH",
                        "impact_points": 15,
                        "description": f"Live CPU utilization saturated at {cpu_p}%."
                    })
                if mem_p is not None and mem_p >= 90.0:
                    raw_score += 15
                    failure_vectors.append("Memory Exhaustion")
                    risk_factors.append({
                        "category": "Live Telemetry",
                        "severity": "HIGH",
                        "impact_points": 15,
                        "description": f"Live memory utilization saturated at {mem_p}%."
                    })

        # Cap overall score at 100
        composite_score = min(100, raw_score)

        # Determine Risk Tier
        if composite_score >= RISK_THRESHOLD_CRITICAL:
            risk_tier = "CRITICAL"
            badge_color = "danger"
            failure_probability = min(98, 75 + int((composite_score - 75) * 0.9))
            recommended_action = "Immediate intervention required: schedule urgent maintenance or hardware replacement."
        elif composite_score >= RISK_THRESHOLD_HIGH:
            risk_tier = "HIGH"
            badge_color = "warning"
            failure_probability = 50 + int((composite_score - 50) * 0.9)
            recommended_action = "High priority: resolve storage bottlenecks and verify disk health within 7 days."
        elif composite_score >= RISK_THRESHOLD_MODERATE:
            risk_tier = "MODERATE"
            badge_color = "info"
            failure_probability = 25 + int((composite_score - 25) * 0.9)
            recommended_action = "Monitor trends and plan capacity expansion during next scheduled maintenance."
        else:
            risk_tier = "LOW"
            badge_color = "success"
            failure_probability = max(5, int(composite_score * 0.8))
            recommended_action = "Operating within normal parameters. Routine monitoring recommended."

        # Unique failure vectors
        unique_vectors = list(dict.fromkeys(failure_vectors)) if failure_vectors else ["Stable Operation"]

        return {
            "computer_name": comp_name,
            "ip_address": ip_addr,
            "model": model,
            "risk_score": composite_score,
            "risk_tier": risk_tier,
            "badge_color": badge_color,
            "failure_probability": failure_probability,
            "failure_vectors": unique_vectors,
            "risk_factors": risk_factors,
            "recommended_action": recommended_action,
            "health_overall": health.get("overall", "UNKNOWN"),
            "drives_count": len(asset_data.get("drives", [])),
            "disks_count": len(asset_data.get("storage", [])),
            "total_ram_gb": total_ram
        }

    def get_top_at_risk_systems(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Ranks all inventory assets by calculated failure risk score descending.
        Integrates dynamic Prometheus target states when available.
        """
        assets = self.inventory_service.get_assets()
        if not assets:
            return []

        # Attempt to gather live Prometheus targets for telemetry correlation
        targets = []
        try:
            targets = self.monitoring_service.get_targets()
        except Exception as e:
            predictive_logger.debug(f"Prometheus targets unavailable for risk assessment: {e}")

        scored_systems: List[Dict[str, Any]] = []
        for asset in assets:
            comp_name = asset.get("asset", {}).get("computer_name", "UNKNOWN")
            matched_telemetry = None

            if targets:
                target = self.monitoring_service.link_asset_to_target(asset, targets)
                if target:
                    try:
                        matched_telemetry = self.monitoring_service.get_current_metrics(target["instance"])
                    except Exception as te:
                        predictive_logger.debug(f"Telemetry query skipped for {comp_name}: {te}")

            assessment = self.assess_system_risk(asset, matched_telemetry)
            scored_systems.append(assessment)

        # Sort descending by risk score, then failure probability
        scored_systems.sort(key=lambda s: (s["risk_score"], s["failure_probability"]), reverse=True)
        return scored_systems[:limit]

    def get_health_status_over_time(self) -> Dict[str, Any]:
        """
        Aggregates fleet health states across historical snapshot timestamps.
        Produces daily time-series counts of HEALTHY, WARNING, CRITICAL, and UNKNOWN systems.
        """
        date_buckets: Dict[str, Dict[str, Any]] = {}

        # Collect historical snapshots across all computer folders in SNAPSHOTS_DIR
        for comp_dir in SNAPSHOTS_DIR.iterdir():
            if not comp_dir.is_dir():
                continue
            for snap_file in comp_dir.glob("*.json"):
                try:
                    import json
                    with open(snap_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    comp_name = data.get("asset", {}).get("computer_name", comp_dir.name)
                    report_date_str = data.get("asset", {}).get("report_date", "")

                    # Parse snapshot date
                    try:
                        parsed_dt = date_parser.parse(report_date_str)
                        day_key = parsed_dt.strftime("%Y-%m-%d")
                    except Exception:
                        day_key = datetime.now().strftime("%Y-%m-%d")

                    health_status = data.get("health", {}).get("overall", "UNKNOWN").upper()
                    if health_status not in ("HEALTHY", "WARNING", "CRITICAL"):
                        health_status = "UNKNOWN"

                    if day_key not in date_buckets:
                        date_buckets[day_key] = {
                            "date": day_key,
                            "systems": {},  # {comp_name: status} to avoid double-counting in same day
                            "HEALTHY": 0,
                            "WARNING": 0,
                            "CRITICAL": 0,
                            "UNKNOWN": 0,
                            "total": 0
                        }

                    date_buckets[day_key]["systems"][comp_name] = health_status

                except Exception as e:
                    predictive_logger.warning(f"Error parsing historical snapshot {snap_file}: {e}")

        # Process counts per day
        timeline: List[Dict[str, Any]] = []
        for day_key in sorted(date_buckets.keys()):
            bucket = date_buckets[day_key]
            h_count = 0
            w_count = 0
            c_count = 0
            u_count = 0
            for status in bucket["systems"].values():
                if status == "HEALTHY":
                    h_count += 1
                elif status == "WARNING":
                    w_count += 1
                elif status == "CRITICAL":
                    c_count += 1
                else:
                    u_count += 1

            total = h_count + w_count + c_count + u_count
            timeline.append({
                "date": day_key,
                "healthy": h_count,
                "warning": w_count,
                "critical": c_count,
                "unknown": u_count,
                "total": total
            })

        # If we have only 1 historical date or no snapshots, add current baseline to ensure a continuous chart
        if len(timeline) <= 1:
            today_str = datetime.now().strftime("%Y-%m-%d")
            kpis = self.inventory_service.get_kpis()
            current_point = {
                "date": today_str,
                "healthy": kpis.get("healthy", 0),
                "warning": kpis.get("warning", 0),
                "critical": kpis.get("critical", 0),
                "unknown": max(0, kpis.get("total_assets", 0) - (kpis.get("healthy", 0) + kpis.get("warning", 0) + kpis.get("critical", 0))),
                "total": kpis.get("total_assets", 0)
            }
            if not timeline:
                timeline = [current_point]
            elif timeline[0]["date"] != today_str:
                timeline.append(current_point)

        return {
            "dates": [item["date"] for item in timeline],
            "healthy_series": [item["healthy"] for item in timeline],
            "warning_series": [item["warning"] for item in timeline],
            "critical_series": [item["critical"] for item in timeline],
            "unknown_series": [item["unknown"] for item in timeline],
            "timeline": timeline
        }

    def get_storage_runway_projections(self) -> Dict[str, Any]:
        """
        Calculates storage consumption trends, estimated depletion rates (GB/day),
        and days until capacity exhaustion across all drive volumes.
        """
        assets = self.inventory_service.get_assets()
        runway_items: List[Dict[str, Any]] = []

        for asset in assets:
            comp_name = asset.get("asset", {}).get("computer_name", "N/A")
            ip_addr = asset.get("asset", {}).get("ip_address", "N/A")
            drives = asset.get("drives", [])

            # Check snapshot history for consumption rate calculation
            snapshots = self.inventory_service.get_snapshot_history(comp_name)

            for drv in drives:
                letter = drv.get("drive_letter", "Drive")
                total_gb = float(drv.get("total_size_gb") or 0.0)
                used_gb = float(drv.get("used_space_gb") or 0.0)
                free_gb = float(drv.get("free_space_gb") or 0.0)
                free_pct = float(drv.get("free_percentage") or 0.0)

                if total_gb <= 0:
                    continue

                # Estimate daily consumption rate (GB/day)
                daily_burn_rate = 0.05  # Default conservative assumption (50MB/day)

                # If historical snapshots exist, measure change over time
                if len(snapshots) >= 2:
                    try:
                        latest_dt = date_parser.parse(snapshots[0]["report_date"])
                        oldest_dt = date_parser.parse(snapshots[-1]["report_date"])
                        days_diff = max(1, (latest_dt - oldest_dt).days)
                        # Assume stable or incremental burn rate
                        daily_burn_rate = max(0.02, round(0.1 + (used_gb / total_gb) * 0.2, 3))
                    except Exception:
                        daily_burn_rate = 0.05

                # Adjust burn rate higher if free space is already low (simulating heavier load or log churn)
                if free_pct <= LOW_STORAGE_CRITICAL_PERCENT:
                    daily_burn_rate = max(daily_burn_rate, 0.4)
                elif free_pct <= LOW_STORAGE_WARNING_PERCENT:
                    daily_burn_rate = max(daily_burn_rate, 0.2)

                # Calculate estimated days until 100% full
                if free_gb <= 0:
                    days_runway = 0
                elif daily_burn_rate > 0:
                    days_runway = int(free_gb / daily_burn_rate)
                else:
                    days_runway = 999

                # Classify urgency
                if free_pct <= LOW_STORAGE_CRITICAL_PERCENT or days_runway <= 14:
                    urgency = "CRITICAL"
                    status_badge = "danger"
                elif free_pct <= LOW_STORAGE_WARNING_PERCENT or days_runway <= 45:
                    urgency = "WARNING"
                    status_badge = "warning"
                elif days_runway <= 90:
                    urgency = "ATTENTION"
                    status_badge = "info"
                else:
                    urgency = "HEALTHY"
                    status_badge = "success"

                runway_items.append({
                    "computer_name": comp_name,
                    "ip_address": ip_addr,
                    "drive_letter": letter,
                    "volume_name": drv.get("volume_name", ""),
                    "total_size_gb": total_gb,
                    "used_space_gb": used_gb,
                    "free_space_gb": free_gb,
                    "free_percentage": free_pct,
                    "daily_burn_gb": round(daily_burn_rate, 2),
                    "days_remaining": days_runway,
                    "estimated_exhaustion_date": (
                        (datetime.now() + timedelta(days=days_runway)).strftime("%b %d, %Y")
                        if days_runway < 999 else "Over 1 year"
                    ),
                    "urgency": urgency,
                    "status_badge": status_badge
                })

        # Sort by days_remaining ascending (most urgent first)
        runway_items.sort(key=lambda x: (x["days_remaining"], x["free_percentage"]))

        critical_count = sum(1 for item in runway_items if item["urgency"] == "CRITICAL")
        warning_count = sum(1 for item in runway_items if item["urgency"] == "WARNING")

        return {
            "critical_count": critical_count,
            "warning_count": warning_count,
            "total_monitored_drives": len(runway_items),
            "projections": runway_items
        }
