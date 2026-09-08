"""
Unit and integration tests for Flask web routes and REST API endpoints.
"""
import io
import pytest
from app import create_app

@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_dashboard_route(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Hardware Inventory" in response.data
    assert b"PC Inventory" in response.data

def test_changes_route(client):
    response = client.get("/changes")
    assert response.status_code == 200
    assert b"Hardware Changes" in response.data

def test_alerts_route(client):
    response = client.get("/alerts")
    assert response.status_code == 200
    assert b"Storage Alerts" in response.data

def test_upload_page_route(client):
    response = client.get("/upload")
    assert response.status_code == 200
    assert b"Upload Health Check Reports" in response.data

def test_pc_details_not_found(client):
    response = client.get("/pc/NON_EXISTENT_MACHINE_123", follow_redirects=True)
    assert response.status_code == 200
    assert b"not found in inventory" in response.data

def test_api_assets(client):
    response = client.get("/api/assets")
    assert response.status_code == 200
    data = response.get_json()
    assert "count" in data
    assert "assets" in data
    assert isinstance(data["assets"], list)

def test_api_changes(client):
    response = client.get("/api/changes")
    assert response.status_code == 200
    data = response.get_json()
    assert "count" in data
    assert "changes" in data

def test_api_alerts(client):
    response = client.get("/api/alerts")
    assert response.status_code == 200
    data = response.get_json()
    assert "storage_alerts" in data
    assert "upgrade_recommendations" in data

def test_upload_txt_via_api(client):
    report_content = b"""WINDOWS COMPLETE HARDWARE SOFTWARE HEALTH CHECK
================================================
IP Address         : 192.168.1.99
Computer Name      : API-TEST-PC
Report Date        : 2026-09-05 12:00:00
Report File        : api_test.txt

==========================================================================================
 COMPUTER / OPERATING SYSTEM
==========================================================================================
Computer Name        : API-TEST-PC
Operating System     : Windows 11 Enterprise
Total Physical RAM   : 16.0 GB
"""
    data = {
        'file': (io.BytesIO(report_content), 'api_test.txt')
    }
    response = client.post('/api/upload', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["processed"] == 1
    assert json_data["results"][0]["computer_name"] == "API-TEST-PC"
