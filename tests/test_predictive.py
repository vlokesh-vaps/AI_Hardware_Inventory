"""
Unit tests for Predictive Analysis Service and AI Insights Service.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

from services.predictive_service import PredictiveService
from services.ai_insight_service import AIInsightService


@pytest.fixture
def mock_inventory():
    """Mock inventory service returning sample assets and snapshots."""
    service = MagicMock()
    service.get_assets.return_value = [
        {
            "asset": {
                "computer_name": "CRITICAL-PC",
                "ip_address": "172.16.10.10",
                "model": "Dell OptiPlex 7070",
                "report_date": "2026-09-01 10:00:00"
            },
            "health": {"overall": "CRITICAL"},
            "total_ram_gb": 8.0,
            "cpu": [{"cores": 2, "status": "OK", "name": "Intel Core i3"}],
            "storage": [
                {
                    "model": "Seagate ST1000",
                    "serial_number": "SN1234",
                    "health_status": "Unhealthy",
                    "operational_status": "Degraded"
                }
            ],
            "drives": [
                {
                    "drive_letter": "C:",
                    "total_size_gb": 500.0,
                    "used_space_gb": 485.0,
                    "free_space_gb": 15.0,
                    "free_percentage": 3.0,
                    "status": "CRITICAL"
                }
            ]
        },
        {
            "asset": {
                "computer_name": "HEALTHY-PC",
                "ip_address": "172.16.10.20",
                "model": "Dell OptiPlex 7090",
                "report_date": "2026-09-01 10:00:00"
            },
            "health": {"overall": "HEALTHY"},
            "total_ram_gb": 32.0,
            "cpu": [{"cores": 8, "status": "OK", "name": "Intel Core i7"}],
            "storage": [
                {
                    "model": "Samsung NVMe 1TB",
                    "serial_number": "SN5678",
                    "health_status": "Healthy",
                    "operational_status": "OK"
                }
            ],
            "drives": [
                {
                    "drive_letter": "C:",
                    "total_size_gb": 1000.0,
                    "used_space_gb": 200.0,
                    "free_space_gb": 800.0,
                    "free_percentage": 80.0,
                    "status": "NORMAL"
                }
            ]
        }
    ]
    service.get_snapshot_history.return_value = [
        {"report_date": "2026-09-05", "overall_health": "CRITICAL"},
        {"report_date": "2026-08-20", "overall_health": "WARNING"}
    ]
    service.get_changes.return_value = []
    service.get_kpis.return_value = {
        "total_assets": 2,
        "healthy": 1,
        "warning": 0,
        "critical": 1
    }
    return service


@pytest.fixture
def mock_monitoring():
    """Mock monitoring service."""
    service = MagicMock()
    service.get_targets.return_value = []
    service.link_asset_to_target.return_value = None
    return service


def test_assess_system_risk_critical(mock_inventory, mock_monitoring):
    """Verifies that a system with critical low storage and failing disk yields high risk score."""
    predictive = PredictiveService(inventory_service=mock_inventory, monitoring_service=mock_monitoring)
    critical_asset = mock_inventory.get_assets()[0]

    risk = predictive.assess_system_risk(critical_asset)

    assert risk["computer_name"] == "CRITICAL-PC"
    assert risk["risk_score"] >= 75
    assert risk["risk_tier"] == "CRITICAL"
    assert "Storage Exhaustion" in risk["failure_vectors"]
    assert "Physical Drive Degradation" in risk["failure_vectors"]
    assert risk["failure_probability"] > 70
    assert len(risk["risk_factors"]) >= 2


def test_assess_system_risk_healthy(mock_inventory, mock_monitoring):
    """Verifies that a well-provisioned system has a low risk score."""
    predictive = PredictiveService(inventory_service=mock_inventory, monitoring_service=mock_monitoring)
    healthy_asset = mock_inventory.get_assets()[1]

    risk = predictive.assess_system_risk(healthy_asset)

    assert risk["computer_name"] == "HEALTHY-PC"
    assert risk["risk_score"] < 25
    assert risk["risk_tier"] == "LOW"
    assert risk["failure_probability"] <= 25


def test_get_top_at_risk_systems_ranking(mock_inventory, mock_monitoring):
    """Verifies ranking orders systems descending by risk score."""
    predictive = PredictiveService(inventory_service=mock_inventory, monitoring_service=mock_monitoring)
    top_systems = predictive.get_top_at_risk_systems(limit=5)

    assert len(top_systems) == 2
    assert top_systems[0]["computer_name"] == "CRITICAL-PC"
    assert top_systems[1]["computer_name"] == "HEALTHY-PC"
    assert top_systems[0]["risk_score"] > top_systems[1]["risk_score"]


def test_get_storage_runway_projections(mock_inventory, mock_monitoring):
    """Verifies storage runway calculations and days remaining sorting."""
    predictive = PredictiveService(inventory_service=mock_inventory, monitoring_service=mock_monitoring)
    runway = predictive.get_storage_runway_projections()

    assert runway["total_monitored_drives"] == 2
    assert runway["critical_count"] >= 1
    # Critical PC drive should have lower remaining days than Healthy PC
    projections = runway["projections"]
    assert projections[0]["computer_name"] == "CRITICAL-PC"
    assert projections[0]["urgency"] == "CRITICAL"


def test_get_health_status_over_time(mock_inventory, mock_monitoring, tmp_path, monkeypatch):
    """Verifies historical timeline aggregator generates consistent data series."""
    # Point SNAPSHOTS_DIR to a temporary folder
    monkeypatch.setattr("services.predictive_service.SNAPSHOTS_DIR", tmp_path)

    predictive = PredictiveService(inventory_service=mock_inventory, monitoring_service=mock_monitoring)
    timeline = predictive.get_health_status_over_time()

    assert "dates" in timeline
    assert "healthy_series" in timeline
    assert "critical_series" in timeline
    assert len(timeline["dates"]) >= 1


def test_ai_insight_service_heuristic_fallback(mock_inventory, mock_monitoring, tmp_path, monkeypatch):
    """Verifies AIInsightService generates structured fallback report when client fails."""
    monkeypatch.setattr("services.ai_insight_service.DATA_DIR", tmp_path)

    ai_service = AIInsightService(
        api_key="test-key",
        inventory_service=mock_inventory,
        monitoring_service=mock_monitoring
    )

    # Force OpenAI client call to raise InternalServerError
    with patch.object(ai_service, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Simulated API Error")
        mock_get_client.return_value = mock_client

        insights = ai_service.generate_fleet_insights(force_refresh=True)

        assert "Heuristic Fallback" in insights["model"]
        assert "Executive Threat & Health Assessment" in insights["content"]
        assert "CRITICAL-PC" in insights["content"]


def test_ai_insight_service_mock_success(mock_inventory, mock_monitoring, tmp_path, monkeypatch):
    """Verifies successful completion from model produces cached payload."""
    monkeypatch.setattr("services.ai_insight_service.DATA_DIR", tmp_path)

    ai_service = AIInsightService(
        api_key="test-key",
        inventory_service=mock_inventory,
        monitoring_service=mock_monitoring
    )

    fake_response = MagicMock()
    fake_choice = MagicMock()
    fake_choice.message.content = "### 1. 🛡️ Executive Threat\nFleet is operating smoothly."
    fake_response.choices = [fake_choice]

    with patch.object(ai_service, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_response
        mock_get_client.return_value = mock_client

        insights = ai_service.generate_fleet_insights(force_refresh=True)

        assert insights["content"] == "### 1. 🛡️ Executive Threat\nFleet is operating smoothly."
        assert insights["model"] == "mistralai/mistral-nemotron"
