"""
NetWatch Enterprise — Test Suite
Run with: pytest tests/ -v
"""

import json
import time
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from main import app, nodes, alerts, THRESHOLDS, _severity, _node_status


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        # Give the background collector a moment
        time.sleep(0.5)
        yield c


# ── Health & Meta ──────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert "uptime" in data


def test_metrics_endpoint(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"node_cpu_usage_percent" in r.data


# ── API — Nodes ───────────────────────────────────────────────────────────────

def test_api_nodes_returns_list(client):
    r = client.get("/api/nodes")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_api_nodes_have_required_fields(client):
    r = client.get("/api/nodes")
    for node in r.get_json():
        assert "id" in node
        assert "name" in node
        assert "status" in node
        assert "ip" in node
        assert "type" in node


def test_api_node_detail(client):
    node_id = list(nodes.keys())[0]
    r = client.get(f"/api/nodes/{node_id}")
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == node_id


def test_api_node_not_found(client):
    r = client.get("/api/nodes/does-not-exist")
    assert r.status_code == 404


# ── API — Alerts ──────────────────────────────────────────────────────────────

def test_api_alerts_returns_list(client):
    r = client.get("/api/alerts")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_api_alert_history(client):
    r = client.get("/api/alerts/history")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_ack_nonexistent_alert(client):
    r = client.post("/api/alerts/fake-id/acknowledge")
    assert r.status_code == 404


# ── API — Summary ─────────────────────────────────────────────────────────────

def test_api_summary_structure(client):
    r = client.get("/api/summary")
    assert r.status_code == 200
    d = r.get_json()
    assert "nodes" in d
    assert "alerts" in d
    assert "avg_cpu" in d
    assert "avg_memory" in d
    assert "uptime" in d


def test_api_summary_node_counts(client):
    r = client.get("/api/summary")
    d = r.get_json()
    total     = d["nodes"]["total"]
    accounted = d["nodes"]["healthy"] + d["nodes"]["warning"] + d["nodes"]["critical"]
    assert accounted == total


# ── API — Thresholds ──────────────────────────────────────────────────────────

def test_get_thresholds(client):
    r = client.get("/api/thresholds")
    assert r.status_code == 200
    d = r.get_json()
    assert "cpu" in d
    assert "memory" in d
    assert "disk" in d


def test_update_thresholds(client):
    payload = {"cpu": {"warning": 65, "critical": 85}}
    r = client.put(
        "/api/thresholds",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert r.status_code == 200
    d = r.get_json()
    assert d["thresholds"]["cpu"]["warning"] == 65
    # Restore
    client.put(
        "/api/thresholds",
        data=json.dumps({"cpu": {"warning": 70, "critical": 90}}),
        content_type="application/json"
    )


# ── Unit — Alert Logic ────────────────────────────────────────────────────────

class TestSeverityLogic:
    def test_no_alert_below_warning(self):
        assert _severity(50, {"warning": 70, "critical": 90}) is None

    def test_warning_triggered(self):
        assert _severity(75, {"warning": 70, "critical": 90}) == "warning"

    def test_critical_triggered(self):
        assert _severity(95, {"warning": 70, "critical": 90}) == "critical"

    def test_exactly_at_warning(self):
        assert _severity(70, {"warning": 70, "critical": 90}) == "warning"

    def test_exactly_at_critical(self):
        assert _severity(90, {"warning": 70, "critical": 90}) == "critical"


class TestNodeStatus:
    def test_healthy_status(self):
        m = {"cpu": 30, "memory": 50, "disk": {"/": 40}, "network_in": 1000, "network_out": 1000, "uptime": 3600}
        assert _node_status(m) == "healthy"

    def test_warning_status_cpu(self):
        m = {"cpu": 75, "memory": 50, "disk": {"/": 40}, "network_in": 1000, "network_out": 1000, "uptime": 3600}
        assert _node_status(m) == "warning"

    def test_critical_status_cpu(self):
        m = {"cpu": 95, "memory": 50, "disk": {"/": 40}, "network_in": 1000, "network_out": 1000, "uptime": 3600}
        assert _node_status(m) == "critical"

    def test_warning_status_memory(self):
        m = {"cpu": 20, "memory": 80, "disk": {"/": 40}, "network_in": 1000, "network_out": 1000, "uptime": 3600}
        assert _node_status(m) == "warning"


# ── Dashboard Route ───────────────────────────────────────────────────────────

def test_dashboard_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"NETWATCH" in r.data
    assert b"<html" in r.data
