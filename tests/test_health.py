"""
Unit tests for Health Service and Recommendation Engine.
Validates health scoring, capacity alerts, and upgrade recommendations.
"""
import pytest
from services.health_service import HealthService
from services.inventory_service import InventoryService

@pytest.fixture
def health_service():
    return HealthService(
        storage_warning_pct=15.0,
        storage_critical_pct=5.0,
        min_ram_gb=16.0,
        min_cpu_cores=4
    )

def test_healthy_status_evaluation(health_service):
    """Computer with good disk health, plenty of free space, and adequate RAM is HEALTHY."""
    pc_data = {
        "asset": {"computer_name": "GOOD-PC"},
        "cpu": [{"name": "Intel Core i7", "cores": 8, "status": "OK"}],
        "ram": [{"capacity_gb": 16.0}],
        "total_ram_gb": 16.0,
        "storage": [
            {"model": "SSD 1TB", "health_status": "Healthy", "operational_status": "OK"}
        ],
        "drives": [
            {"drive_letter": "C:", "free_percentage": 45.0, "status": "NORMAL"}
        ],
        "motherboard": {"status": "OK"}
    }
    result = health_service.evaluate_health(pc_data)
    assert result["overall"] == "HEALTHY"
    assert len(result["issues"]) == 0
    assert len(result["warnings"]) == 0
    assert len(result["recommendations"]) == 0

def test_warning_on_low_disk_space(health_service):
    """Free disk percentage between 5% and 15% triggers a WARNING."""
    pc_data = {
        "asset": {"computer_name": "WARN-PC"},
        "cpu": [{"name": "Intel Core i7", "cores": 8, "status": "OK"}],
        "ram": [{"capacity_gb": 16.0}],
        "total_ram_gb": 16.0,
        "storage": [
            {"model": "SSD 1TB", "health_status": "Healthy", "operational_status": "OK"}
        ],
        "drives": [
            {"drive_letter": "C:", "free_percentage": 12.0, "status": "WARNING"}
        ],
        "motherboard": {"status": "OK"}
    }
    result = health_service.evaluate_health(pc_data)
    assert result["overall"] == "WARNING"
    assert result["storage_alert_count"] == 1
    assert any("Drive C: low free space" in w for w in result["warnings"])

def test_critical_on_unhealthy_disk(health_service):
    """Physical disk reporting 'Unhealthy' or 'Degraded' triggers CRITICAL."""
    pc_data = {
        "asset": {"computer_name": "FAILING-DISK-PC"},
        "cpu": [{"name": "Intel Core i7", "cores": 8, "status": "OK"}],
        "ram": [{"capacity_gb": 16.0}],
        "total_ram_gb": 16.0,
        "storage": [
            {"model": "HDD 1TB", "health_status": "Unhealthy", "operational_status": "Degraded", "serial_number": "BAD123"}
        ],
        "drives": [
            {"drive_letter": "C:", "free_percentage": 50.0, "status": "NORMAL"}
        ]
    }
    result = health_service.evaluate_health(pc_data)
    assert result["overall"] == "CRITICAL"
    assert len(result["issues"]) >= 1
    assert any("BAD123" in issue for issue in result["issues"])

def test_critical_on_critically_low_free_space(health_service):
    """Free disk space <= 5% triggers CRITICAL."""
    pc_data = {
        "asset": {"computer_name": "FULL-DISK-PC"},
        "cpu": [{"name": "Intel Core i7", "cores": 8, "status": "OK"}],
        "ram": [{"capacity_gb": 16.0}],
        "total_ram_gb": 16.0,
        "storage": [
            {"model": "SSD 1TB", "health_status": "Healthy", "operational_status": "OK"}
        ],
        "drives": [
            {"drive_letter": "C:", "free_percentage": 3.2, "status": "CRITICAL"}
        ]
    }
    result = health_service.evaluate_health(pc_data)
    assert result["overall"] == "CRITICAL"
    assert any("Drive C: critical free space" in issue for issue in result["issues"])

def test_unknown_status_on_empty_data(health_service):
    """Empty hardware data results in UNKNOWN status without raising exceptions."""
    result = health_service.evaluate_health({"asset": {"computer_name": "EMPTY-PC"}})
    assert result["overall"] == "UNKNOWN"

def test_ram_upgrade_recommendation(health_service):
    """RAM below 16 GB generates an UpgradeRecommendation."""
    pc_data = {
        "asset": {"computer_name": "LOW-RAM-PC"},
        "cpu": [{"name": "Intel Core i5", "cores": 4, "status": "OK"}],
        "ram": [{"capacity_gb": 8.0}],
        "total_ram_gb": 8.0,
        "storage": [{"model": "SSD", "health_status": "Healthy", "operational_status": "OK"}],
        "drives": [{"drive_letter": "C:", "free_percentage": 50.0, "status": "NORMAL"}]
    }
    result = health_service.evaluate_health(pc_data)
    assert result["overall"] == "WARNING"
    recs = result["recommendations"]
    assert len(recs) == 1
    rec = recs[0]
    assert rec["component"] == "RAM"
    assert "8.0 GB" in rec["current_value"]
    assert "at least 16.0 GB" in rec["recommended_action"]
