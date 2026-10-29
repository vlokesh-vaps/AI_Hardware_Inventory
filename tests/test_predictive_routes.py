"""
Integration tests for Predictive Analysis and AI Insights routes in app.py.
"""
from unittest.mock import patch, MagicMock
import pytest
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def mock_ai_insights():
    """Ensures route tests run lightning-fast without depending on external NVIDIA network latency."""
    with patch("services.ai_insight_service.AIInsightService.generate_fleet_insights") as mock_gen:
        mock_gen.return_value = {
            "model": "mistralai/mistral-nemotron",
            "timestamp": 1757400000,
            "generated_at": "2026-09-09 10:00:00",
            "elapsed_seconds": 1.23,
            "summary_context": {
                "fleet_kpis": {"total_assets": 2},
                "top_at_risk_systems": [],
                "storage_exhaustion_alerts": []
            },
            "content": "### 1. 🛡️ Executive Threat & Health Assessment\nFleet is operational.\n\n### 2. ⚠️ At-Risk Systems\n2F-S03 at risk."
        }
        yield mock_gen


def test_predictive_page_renders_200(client):
    """Verifies that the /predictive dashboard loads with 200 OK and renders key elements."""
    response = client.get("/predictive")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Predictive Fleet Analysis & AI Insights" in html
    assert "Top At-Risk Systems" in html
    assert "healthTimelineChart" in html
    assert "storageRunwayChart" in html
    assert "Autonomous Infrastructure Diagnostic Report" in html
    assert "Ask NVIDIA Nemotron Infrastructure AI" in html


def test_dashboard_contains_predictive_spotlight(client):
    """Verifies that the main dashboard includes the predictive spotlight widget."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "predictive-spotlight" in html
    assert "Predictive Failure Risk & AI Diagnostics" in html
    assert "Open Predictive & AI Center" in html


def test_api_predictive_at_risk(client):
    """Verifies /api/predictive/at-risk returns ranked systems JSON."""
    response = client.get("/api/predictive/at-risk?limit=5")
    assert response.status_code == 200
    data = response.get_json()
    assert "count" in data
    assert "systems" in data
    assert isinstance(data["systems"], list)


def test_api_predictive_timeline(client):
    """Verifies /api/predictive/timeline returns timeline series and storage runway JSON."""
    response = client.get("/api/predictive/timeline")
    assert response.status_code == 200
    data = response.get_json()
    assert "health_timeline" in data
    assert "storage_runway" in data
    assert "dates" in data["health_timeline"]
    assert "projections" in data["storage_runway"]


def test_api_ai_insights(client):
    """Verifies /api/ai/insights returns structured insight payload."""
    response = client.get("/api/ai/insights")
    assert response.status_code == 200
    data = response.get_json()
    assert "content" in data
    assert "model" in data
    assert "generated_at" in data


def test_api_ai_ask_validation_and_response(client):
    """Verifies question validation and response handling on /api/ai/ask."""
    # Test missing question returns 400
    resp_empty = client.post("/api/ai/ask", json={})
    assert resp_empty.status_code == 400

    # Test valid question with mocked AI response
    with patch("services.ai_insight_service.AIInsightService.ask_ai_question") as mock_ask:
        mock_ask.return_value = {
            "question": "Which drive is at risk?",
            "answer": "Drive C on 2F-S03 has 23.2% free space.",
            "model": "mistralai/mistral-nemotron",
            "elapsed_seconds": 0.45,
            "success": True
        }

        resp = client.post("/api/ai/ask", json={"question": "Which drive is at risk?"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "2F-S03" in data["answer"]
