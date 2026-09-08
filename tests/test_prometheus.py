"""
Comprehensive Unit and Integration Tests for Prometheus Monitoring (Pipeline B).
Tests client, services, target discovery, metrics calculations, error handling,
caching, and REST API routes with zero reliance on live network endpoints.
"""
import io
import json
import time
import urllib.error
from unittest.mock import patch, MagicMock
import pytest

from app import create_app
from services.prometheus_client import (
    PrometheusClient,
    PrometheusClientError,
    PrometheusConnectionError,
    PrometheusTimeoutError,
    PrometheusQueryError
)
from services.monitoring_service import MonitoringService


@pytest.fixture
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def prom_client():
    return PrometheusClient(base_url="http://mock-prometheus:9090", timeout=2)


@pytest.fixture
def mon_service(prom_client):
    return MonitoringService(client=prom_client, cache_ttl=5)


# ============================================================================
# 1. PROMETHEUS CLIENT TESTS
# ============================================================================

def test_client_init(prom_client):
    assert prom_client.base_url == "http://mock-prometheus:9090"
    assert prom_client.timeout == 2


def test_client_successful_query(prom_client):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_payload = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"__name__": "up", "instance": "192.168.1.10:9182", "name": "PC-01"},
                    "value": [1788846339.0, "1"]
                }
            ]
        }
    }
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        res = prom_client.query('up{job="windows"}')
        assert res["status"] == "success"
        assert len(res["data"]["result"]) == 1
        assert res["data"]["result"][0]["metric"]["name"] == "PC-01"


def test_client_connection_error(prom_client):
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        with pytest.raises(PrometheusConnectionError) as exc_info:
            prom_client.query("up")
        assert exc_info.value.code == "PROMETHEUS_UNAVAILABLE"


def test_client_timeout_error(prom_client):
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        with pytest.raises(PrometheusTimeoutError) as exc_info:
            prom_client.query("up")
        assert exc_info.value.code == "PROMETHEUS_TIMEOUT"


def test_client_http_bad_request(prom_client):
    err_body = json.dumps({"status": "error", "errorType": "bad_data", "error": "parse error"}).encode("utf-8")
    mock_err = urllib.error.HTTPError(
        url="http://mock-prometheus:9090",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=io.BytesIO(err_body)
    )
    with patch("urllib.request.urlopen", side_effect=mock_err):
        with pytest.raises(PrometheusQueryError) as exc_info:
            prom_client.query("invalid{{{")
        assert exc_info.value.code == "INVALID_QUERY"


def test_client_invalid_json_response(prom_client):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b"<html>Server Error</html>"
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        with pytest.raises(PrometheusClientError) as exc_info:
            prom_client.query("up")
        assert exc_info.value.code == "INVALID_RESPONSE"


# ============================================================================
# 2. TARGET DISCOVERY & UP/DOWN RULES
# ============================================================================

def test_target_discovery_up_and_down(mon_service):
    mock_payload = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"__name__": "up", "instance": "172.16.10.157:9182", "name": "2F-S02", "job": "windows"},
                    "value": [1788846339.0, "1"]
                },
                {
                    "metric": {"__name__": "up", "instance": "172.16.10.34:9182", "name": "Lokesh", "job": "windows"},
                    "value": [1788846339.0, "0"]
                }
            ]
        }
    }
    with patch.object(mon_service.client, "query", return_value=mock_payload):
        targets = mon_service.get_targets(bypass_cache=True)
        assert len(targets) == 2

        # Verify 2F-S02 (up=1)
        t_online = next(t for t in targets if t["name"] == "2F-S02")
        assert t_online["online"] is True
        assert t_online["instance"] == "172.16.10.157:9182"

        # Verify Lokesh (up=0)
        t_offline = next(t for t in targets if t["name"] == "Lokesh")
        assert t_offline["online"] is False
        assert t_offline["instance"] == "172.16.10.34:9182"


def test_offline_target_metrics_not_hardware_failure(mon_service):
    """Verifies up=0 returns status=OFFLINE and never classifies as hardware failure."""
    mock_targets = [
        {"name": "Lokesh", "instance": "172.16.10.34:9182", "job": "windows", "online": False}
    ]
    with patch.object(mon_service, "get_targets", return_value=mock_targets):
        res = mon_service.get_current_metrics("172.16.10.34:9182", bypass_cache=True)

        assert res["online"] is False
        assert res["status"] == "OFFLINE"
        assert "unreachable" in res["status_detail"].lower() or "offline" in res["status_detail"].lower()
        assert res["metrics"]["cpu_percent"] is None
        assert res["metrics"]["memory_percent"] is None
        assert res["metrics"]["disk_percent"] is None


# ============================================================================
# 3. METRIC CALCULATIONS & PARSING
# ============================================================================

def test_current_metrics_calculation(mon_service):
    """Verifies CPU, RAM, Disk, Uptime, and Network calculations for an online target."""
    mock_targets = [
        {"name": "2F-S02", "instance": "172.16.10.157:9182", "job": "windows", "online": True}
    ]

    def mock_query(promql, **kwargs):
        if "rate(windows_cpu_time_total" in promql:
            return {"status": "success", "data": {"result": [{"value": [100.0, "7.45"]}]}}
        elif "windows_cs_physical_memory_bytes" in promql:
            return {"status": "success", "data": {"result": [{"value": [100.0, "8589934592"]}]}}  # 8 GB
        elif "windows_os_physical_memory_free_bytes" in promql:
            return {"status": "success", "data": {"result": [{"value": [100.0, "3435973836"]}]}}  # ~3.2 GB
        elif "windows_logical_disk_size_bytes" in promql:
            return {"status": "success", "data": {"result": [
                {"metric": {"volume": "C:"}, "value": [100.0, "100000000000"]},
                {"metric": {"volume": "D:"}, "value": [100.0, "200000000000"]}
            ]}}
        elif "windows_logical_disk_free_bytes" in promql:
            return {"status": "success", "data": {"result": [
                {"metric": {"volume": "C:"}, "value": [100.0, "40000000000"]},  # 60% used
                {"metric": {"volume": "D:"}, "value": [100.0, "150000000000"]}  # 25% used
            ]}}
        elif "windows_system_system_up_time" in promql:
            return {"status": "success", "data": {"result": [{"value": [100.0, "1787113135.5"]}]}}
        elif "windows_service_state" in promql:
            return {"status": "success", "data": {"result": [
                {"metric": {"exported_name": "Spooler", "state": "running"}, "value": [100.0, "1"]},
                {"metric": {"exported_name": "LanmanServer", "state": "running"}, "value": [100.0, "1"]}
            ]}}
        elif "windows_os_processes" in promql:
            return {"status": "success", "data": {"result": [{"value": [100.0, "142"]}]}}
        elif "windows_net_bytes" in promql:
            return {"status": "success", "data": {"result": [{"metric": {"nic": "Ethernet"}, "value": [100.0, "51200"]}]}}
        elif "windows_logical_disk_read_bytes_total" in promql:
            return {"status": "success", "data": {"result": [{"value": [100.0, "10240"]}]}}
        elif "windows_logical_disk_write_bytes_total" in promql:
            return {"status": "success", "data": {"result": [{"value": [100.0, "20480"]}]}}
        return {"status": "success", "data": {"result": []}}

    with patch.object(mon_service, "get_targets", return_value=mock_targets):
        with patch.object(mon_service.client, "query", side_effect=mock_query):
            res = mon_service.get_current_metrics("172.16.10.157:9182", bypass_cache=True)

            assert res["online"] is True
            assert res["status"] == "ONLINE"
            metrics = res["metrics"]

            # CPU: 7.45%
            assert metrics["cpu_percent"] == 7.45

            # RAM: 100 * (1 - 3435973836 / 8589934592) = 60.0%
            assert metrics["memory_percent"] == 60.0
            assert metrics["memory_total_bytes"] == 8589934592

            # Disks: 2 drives (C: used 60%, D: used 25%)
            assert len(metrics["disk"]) == 2
            c_drive = next(d for d in metrics["disk"] if d["drive"] == "C:")
            assert c_drive["used_percent"] == 60.0

            # Uptime: computed from seconds
            assert metrics["uptime_seconds"] is not None
            assert metrics["uptime_display"] != "N/A"

            # Temperature: verified null
            assert metrics["temperature"] is None

            # Services: Spooler is running
            spooler = next(s for s in metrics["services"] if s["service"] == "Spooler")
            assert spooler["status"] == "running"

            # Processes: 142
            assert metrics["processes"]["total_count"] == 142


def test_missing_metrics_graceful_null(mon_service):
    """Verifies that missing metrics return None/null instead of fake values."""
    mock_targets = [
        {"name": "2F-S02", "instance": "172.16.10.157:9182", "job": "windows", "online": True}
    ]

    with patch.object(mon_service, "get_targets", return_value=mock_targets):
        with patch.object(mon_service.client, "query", return_value={"status": "success", "data": {"result": []}}):
            res = mon_service.get_current_metrics("172.16.10.157:9182", bypass_cache=True)

            assert res["metrics"]["cpu_percent"] is None
            assert res["metrics"]["memory_percent"] is None
            assert res["metrics"]["disk_percent"] is None
            assert res["metrics"]["temperature"] is None
            assert res["metrics"]["uptime_display"] == "N/A"


def test_instance_format_validation(mon_service):
    """Verifies instance validation blocks potential PromQL injections."""
    assert mon_service.validate_instance("172.16.10.157:9182") is True
    assert mon_service.validate_instance("hostname.local:9182") is True
    assert mon_service.validate_instance("invalid_ip") is False
    assert mon_service.validate_instance('172.16.10.157:9182", job="windows') is False


def test_historical_metrics(mon_service):
    """Verifies range PromQL execution and data point formatting."""
    mock_payload = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"instance": "172.16.10.157:9182"},
                    "values": [
                        [1788843280, "7.47"],
                        [1788843340, "8.12"]
                    ]
                }
            ]
        }
    }
    with patch.object(mon_service.client, "query_range", return_value=mock_payload):
        hist = mon_service.get_historical_metrics("172.16.10.157:9182", metric_name="cpu", time_range="1h")
        assert hist["instance"] == "172.16.10.157:9182"
        assert hist["metric"] == "cpu"
        assert hist["points_count"] == 2
        assert hist["data_points"][0]["value"] == 7.47


# ============================================================================
# 4. REST API ROUTES TESTS
# ============================================================================

def test_api_monitoring_targets(client):
    mock_targets = [
        {"name": "2F-S02", "instance": "172.16.10.157:9182", "job": "windows", "online": True}
    ]
    with patch("services.monitoring_service.MonitoringService.get_targets", return_value=mock_targets):
        res = client.get("/api/monitoring/targets")
        assert res.status_code == 200
        data = res.get_json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "2F-S02"
        assert data["data"][0]["online"] is True


def test_api_monitoring_current(client):
    mock_metrics = {
        "name": "2F-S02",
        "instance": "172.16.10.157:9182",
        "online": True,
        "status": "ONLINE",
        "status_detail": "Operating normally",
        "metrics": {
            "cpu_percent": 8.5,
            "memory_percent": 55.0,
            "disk_percent": 45.0,
            "network": {"receive_bytes_sec": 1024.0, "send_bytes_sec": 2048.0},
            "uptime_seconds": 12345,
            "temperature": None
        },
        "timestamp": 1788846500
    }
    with patch("services.monitoring_service.MonitoringService.get_current_metrics", return_value=mock_metrics):
        res = client.get("/api/monitoring/172.16.10.157:9182/current")
        assert res.status_code == 200
        data = res.get_json()
        assert data["name"] == "2F-S02"
        assert data["metrics"]["cpu_percent"] == 8.5
        assert data["metrics"]["temperature"] is None
        assert data["metrics"]["network_receive_bytes_sec"] == 1024.0


def test_api_monitoring_invalid_instance(client):
    res = client.get("/api/monitoring/malicious_payload_no_port/current")
    assert res.status_code == 400
    data = res.get_json()
    assert data["error"]["code"] == "INVALID_INSTANCE"


def test_api_monitoring_history(client):
    mock_hist = {
        "instance": "172.16.10.157:9182",
        "metric": "cpu",
        "range": "1h",
        "step": "30s",
        "points_count": 1,
        "data_points": [{"timestamp": 1788843280, "value": 7.45}]
    }
    with patch("services.monitoring_service.MonitoringService.get_historical_metrics", return_value=mock_hist):
        res = client.get("/api/monitoring/172.16.10.157:9182/history?metric=cpu&range=1h")
        assert res.status_code == 200
        data = res.get_json()
        assert data["metric"] == "cpu"
        assert len(data["data_points"]) == 1


def test_monitoring_web_route(client):
    """Verifies that the /monitoring Web UI renders successfully."""
    res = client.get("/monitoring")
    assert res.status_code == 200
    assert b"Live Hardware Monitoring" in res.data
    assert b"Telemetry Trends" in res.data
