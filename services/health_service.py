"""
Centralized Health and Recommendation Service.
Evaluates hardware health, capacity alerts, and upgrade recommendations using configurable rules.
"""
from typing import Dict, Any, List
from config import (
    LOW_STORAGE_WARNING_PERCENT,
    LOW_STORAGE_CRITICAL_PERCENT,
    RECOMMENDED_MIN_RAM_GB,
    RECOMMENDED_MIN_CPU_CORES,
    app_logger
)
from models.schemas import HealthStatus, UpgradeRecommendation

class HealthService:
    """Evaluates PC health, detects capacity warnings, and generates upgrade recommendations."""

    def __init__(
        self,
        storage_warning_pct: float = LOW_STORAGE_WARNING_PERCENT,
        storage_critical_pct: float = LOW_STORAGE_CRITICAL_PERCENT,
        min_ram_gb: float = RECOMMENDED_MIN_RAM_GB,
        min_cpu_cores: int = RECOMMENDED_MIN_CPU_CORES
    ):
        self.storage_warning_pct = storage_warning_pct
        self.storage_critical_pct = storage_critical_pct
        self.min_ram_gb = min_ram_gb
        self.min_cpu_cores = min_cpu_cores

    def evaluate_health(self, pc_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates overall health status for a normalized PC data record.
        Returns a dictionary representing HealthStatus.
        """
        comp_name = pc_data.get("asset", {}).get("computer_name", "UNKNOWN-PC")
        issues: List[str] = []
        warnings: List[str] = []
        recommendations: List[UpgradeRecommendation] = []
        storage_alerts = 0

        # Check if report has minimal required info
        if not pc_data.get("cpu") and not pc_data.get("ram") and not pc_data.get("storage"):
            return HealthStatus(
                overall="UNKNOWN",
                issues=["Report contains insufficient hardware information to determine health."],
                warnings=[],
                storage_alert_count=0,
                upgrade_required_count=0,
                recommendations=[]
            ).to_dict()

        # 1. Storage Health Check (Physical disks)
        for disk in pc_data.get("storage", []):
            h_stat = str(disk.get("health_status", "")).strip().lower()
            op_stat = str(disk.get("operational_status", "")).strip().lower()
            model = disk.get("model", "Disk")
            serial = disk.get("serial_number", "N/A")

            if h_stat in ("unhealthy", "failing", "error", "bad") or op_stat in ("error", "failed", "degraded"):
                issues.append(f"Storage disk '{model}' (S/N: {serial}) status is '{disk.get('health_status')} / {disk.get('operational_status')}'")
            elif h_stat in ("warning", "caution") or op_stat in ("warning", "caution"):
                warnings.append(f"Storage disk '{model}' (S/N: {serial}) has warning status '{disk.get('health_status')}'")

        # 2. Drive Capacity Check (Drive partitions)
        for drv in pc_data.get("drives", []):
            free_pct = drv.get("free_percentage")
            letter = drv.get("drive_letter", "Drive")
            free_gb = drv.get("free_space_gb", 0)

            if free_pct is not None:
                if free_pct <= self.storage_critical_pct:
                    issues.append(f"Drive {letter} critical free space: only {free_pct}% ({free_gb} GB) remaining.")
                    storage_alerts += 1
                    recommendations.append(UpgradeRecommendation(
                        component="Storage",
                        reason=f"Drive {letter} has critical low free space ({free_pct}% free)",
                        current_value=f"{free_pct}% free ({free_gb} GB)",
                        recommended_action=f"Urgent: Free up disk space or expand partition on {letter}"
                    ))
                elif free_pct <= self.storage_warning_pct:
                    warnings.append(f"Drive {letter} low free space: {free_pct}% ({free_gb} GB) remaining.")
                    storage_alerts += 1
                    recommendations.append(UpgradeRecommendation(
                        component="Storage",
                        reason=f"Drive {letter} free space is below {self.storage_warning_pct}% threshold",
                        current_value=f"{free_pct}% free ({free_gb} GB)",
                        recommended_action=f"Clean up temporary files or expand volume {letter}"
                    ))

        # 3. CPU Status & Core Count
        for cpu in pc_data.get("cpu", []):
            stat = str(cpu.get("status", "")).strip().lower()
            name = cpu.get("name", "CPU")
            cores = cpu.get("cores")

            if stat in ("error", "failed", "degraded"):
                issues.append(f"CPU '{name}' status is '{cpu.get('status')}'")
            elif stat in ("warning", "caution"):
                warnings.append(f"CPU '{name}' reported warning status '{cpu.get('status')}'")

            if cores and cores < self.min_cpu_cores:
                warnings.append(f"CPU core count ({cores}) is below recommended {self.min_cpu_cores} cores.")
                recommendations.append(UpgradeRecommendation(
                    component="CPU",
                    reason=f"System processor has only {cores} core(s)",
                    current_value=f"{cores} cores",
                    recommended_action=f"Consider upgrading to a processor with at least {self.min_cpu_cores} cores"
                ))

        # 4. RAM Check & Recommendation
        total_ram = pc_data.get("total_ram_gb")
        if total_ram is not None and total_ram < self.min_ram_gb:
            warnings.append(f"Total RAM ({total_ram} GB) is below recommended {self.min_ram_gb} GB.")
            recommendations.append(UpgradeRecommendation(
                component="RAM",
                reason=f"Total system RAM ({total_ram} GB) is lower than enterprise standard ({self.min_ram_gb} GB)",
                current_value=f"{total_ram} GB",
                recommended_action=f"Upgrade RAM capacity to at least {self.min_ram_gb} GB"
            ))

        # 5. Motherboard / BIOS Status
        mb_stat = str(pc_data.get("motherboard", {}).get("status", "")).strip().lower()
        if mb_stat in ("error", "failed"):
            issues.append(f"Motherboard status is '{pc_data.get('motherboard', {}).get('status')}'")

        # Determine overall status
        if issues:
            overall = "CRITICAL"
        elif warnings:
            overall = "WARNING"
        else:
            overall = "HEALTHY"

        app_logger.debug(f"Health for {comp_name}: {overall} ({len(issues)} issues, {len(warnings)} warnings)")

        return HealthStatus(
            overall=overall,
            issues=issues,
            warnings=warnings,
            storage_alert_count=storage_alerts,
            upgrade_required_count=len(recommendations),
            recommendations=recommendations
        ).to_dict()
