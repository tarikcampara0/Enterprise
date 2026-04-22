"""
Enterprise Network Monitoring & Alerting System
Main Flask Application
"""

import os
import json
import time
import random
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, Response
from prometheus_client import (
    Counter, Gauge, Histogram, generate_latest,
    CollectorRegistry, CONTENT_TYPE_LATEST
)
import psutil
import logging

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

# ── Prometheus Metrics ────────────────────────────────────────────────────────
registry = CollectorRegistry()

cpu_usage_gauge        = Gauge("node_cpu_usage_percent",      "CPU usage %",           ["host"], registry=registry)
memory_usage_gauge     = Gauge("node_memory_usage_percent",   "Memory usage %",        ["host"], registry=registry)
disk_usage_gauge       = Gauge("node_disk_usage_percent",     "Disk usage %",          ["host", "mount"], registry=registry)
network_in_gauge       = Gauge("node_network_bytes_in",       "Network bytes in/s",    ["host", "interface"], registry=registry)
network_out_gauge      = Gauge("node_network_bytes_out",      "Network bytes out/s",   ["host", "interface"], registry=registry)
http_requests_total    = Counter("app_http_requests_total",   "Total HTTP requests",   ["method", "endpoint", "status"], registry=registry)
response_time_hist     = Histogram("app_response_time_seconds","HTTP response time",   ["endpoint"], registry=registry)
active_alerts_gauge    = Gauge("monitoring_active_alerts",    "Active alert count",    ["severity"], registry=registry)
uptime_gauge           = Gauge("node_uptime_seconds",         "Node uptime seconds",   ["host"], registry=registry)

# ── Alert Thresholds ──────────────────────────────────────────────────────────
THRESHOLDS = {
    "cpu":    {"warning": 70, "critical": 90},
    "memory": {"warning": 75, "critical": 90},
    "disk":   {"warning": 80, "critical": 95},
    "network_in":  {"warning": 80_000_000, "critical": 95_000_000},
    "network_out": {"warning": 80_000_000, "critical": 95_000_000},
}

# ── In-Memory State ───────────────────────────────────────────────────────────
alerts: list[dict]          = []
alert_history: list[dict]   = []
metrics_history: dict       = {}
nodes: dict                 = {}
START_TIME = time.time()

# ── Simulated Node Definitions ────────────────────────────────────────────────
SIMULATED_NODES = [
    {"id": "web-01",    "name": "Web Server 01",      "type": "web",      "ip": "10.0.1.10"},
    {"id": "web-02",    "name": "Web Server 02",      "type": "web",      "ip": "10.0.1.11"},
    {"id": "db-01",     "name": "Database Primary",   "type": "database", "ip": "10.0.2.10"},
    {"id": "db-02",     "name": "Database Replica",   "type": "database", "ip": "10.0.2.11"},
    {"id": "cache-01",  "name": "Redis Cache",        "type": "cache",    "ip": "10.0.3.10"},
    {"id": "lb-01",     "name": "Load Balancer",      "type": "network",  "ip": "10.0.0.5"},
    {"id": "monitor",   "name": "Monitor Host",       "type": "monitor",  "ip": "127.0.0.1"},
]

def _init_nodes():
    for n in SIMULATED_NODES:
        nodes[n["id"]] = {
            **n,
            "status": "healthy",
            "last_seen": datetime.utcnow().isoformat(),
            "metrics": {},
        }
        metrics_history[n["id"]] = []

_init_nodes()

# ── Metric Simulation ─────────────────────────────────────────────────────────
_sim_state: dict = {}   # per-node drifting state

def _sim_metric(node_id: str, key: str, base: float, std: float,
                lo: float = 0.0, hi: float = 100.0) -> float:
    """Random-walk simulation so values drift smoothly."""
    state = _sim_state.setdefault(node_id, {})
    prev  = state.get(key, base)
    val   = prev + random.gauss(0, std)
    val   = max(lo, min(hi, val))
    state[key] = val
    return round(val, 2)

def collect_local_metrics() -> dict:
    """Collect real metrics from the monitor host."""
    net = psutil.net_io_counters()
    partitions = psutil.disk_partitions()
    disk_usage = {}
    for p in partitions:
        try:
            usage = psutil.disk_usage(p.mountpoint)
            disk_usage[p.mountpoint] = round(usage.percent, 2)
        except PermissionError:
            pass
    return {
        "cpu":    round(psutil.cpu_percent(interval=None), 2),
        "memory": round(psutil.virtual_memory().percent, 2),
        "disk":   disk_usage,
        "network_in":  net.bytes_recv,
        "network_out": net.bytes_sent,
        "uptime": round(time.time() - psutil.boot_time(), 0),
    }

def collect_simulated_metrics(node_id: str) -> dict:
    profiles = {
        "web":      {"cpu_base": 35, "mem_base": 45, "std": 8},
        "database": {"cpu_base": 55, "mem_base": 70, "std": 6},
        "cache":    {"cpu_base": 20, "mem_base": 85, "std": 4},
        "network":  {"cpu_base": 15, "mem_base": 30, "std": 5},
        "monitor":  {"cpu_base": 25, "mem_base": 40, "std": 5},
    }
    ntype   = nodes[node_id]["type"]
    profile = profiles.get(ntype, profiles["monitor"])

    cpu = _sim_metric(node_id, "cpu", profile["cpu_base"], profile["std"], 0, 100)
    mem = _sim_metric(node_id, "mem", profile["mem_base"], profile["std"], 0, 100)
    # Occasionally spike to simulate incidents
    if random.random() < 0.02:
        cpu = min(100, cpu + random.uniform(20, 40))
    return {
        "cpu":    cpu,
        "memory": mem,
        "disk":   {"/": _sim_metric(node_id, "disk_root", 45, 1, 0, 100)},
        "network_in":  round(_sim_metric(node_id, "net_in",  5_000_000, 1_000_000, 0, 100_000_000)),
        "network_out": round(_sim_metric(node_id, "net_out", 3_000_000,   800_000, 0, 100_000_000)),
        "uptime":      round(time.time() - START_TIME),
    }

# ── Alert Engine ──────────────────────────────────────────────────────────────

def _severity(value: float, thr: dict) -> str | None:
    if value >= thr["critical"]: return "critical"
    if value >= thr["warning"]:  return "warning"
    return None

def check_alerts(node_id: str, metrics: dict):
    global alerts
    now = datetime.utcnow().isoformat()
    new_alerts: list[dict] = []

    checks = [
        ("cpu",    metrics.get("cpu", 0),    THRESHOLDS["cpu"],    "CPU usage"),
        ("memory", metrics.get("memory", 0), THRESHOLDS["memory"], "Memory usage"),
    ]
    for mount, pct in (metrics.get("disk") or {}).items():
        checks.append((f"disk_{mount}", pct, THRESHOLDS["disk"], f"Disk {mount}"))

    for key, value, thr, label in checks:
        sev = _severity(value, thr)
        if sev:
            alert_id = f"{node_id}_{key}"
            # dedup
            if not any(a["id"] == alert_id for a in alerts):
                alert = {
                    "id":        alert_id,
                    "node_id":   node_id,
                    "node_name": nodes[node_id]["name"],
                    "metric":    key,
                    "label":     label,
                    "value":     value,
                    "threshold": thr[sev],
                    "severity":  sev,
                    "timestamp": now,
                    "message":   f"{label} on {nodes[node_id]['name']} is {value:.1f}% (threshold: {thr[sev]}%)",
                    "acknowledged": False,
                }
                new_alerts.append(alert)
                alert_history.append({**alert, "resolved": False})
                logger.warning("ALERT [%s] %s", sev.upper(), alert["message"])

    # resolve cleared alerts
    alerts = [a for a in alerts if not _is_resolved(a, metrics)]
    alerts.extend(new_alerts)

    # Update prometheus gauges
    active_alerts_gauge.labels(severity="warning").set(
        sum(1 for a in alerts if a["severity"] == "warning"))
    active_alerts_gauge.labels(severity="critical").set(
        sum(1 for a in alerts if a["severity"] == "critical"))

def _is_resolved(alert: dict, metrics: dict) -> bool:
    key = alert["metric"]
    if key == "cpu":    val = metrics.get("cpu", 0)
    elif key == "memory": val = metrics.get("memory", 0)
    elif key.startswith("disk_"):
        mount = key[5:]
        val = (metrics.get("disk") or {}).get(mount, 0)
    else:
        return False
    thr = THRESHOLDS.get(key.split("_")[0], THRESHOLDS["cpu"])
    return val < thr["warning"]

# ── Background Collector Thread ───────────────────────────────────────────────

def _collection_loop():
    """Runs in background — collects metrics every 15 s."""
    while True:
        for node_id, node in nodes.items():
            try:
                if node_id == "monitor":
                    m = collect_local_metrics()
                else:
                    m = collect_simulated_metrics(node_id)

                node["metrics"]   = m
                node["last_seen"] = datetime.utcnow().isoformat()
                node["status"]    = _node_status(m)

                # push to prometheus
                host = node["ip"]
                cpu_usage_gauge.labels(host=host).set(m["cpu"])
                memory_usage_gauge.labels(host=host).set(m["memory"])
                for mount, pct in (m.get("disk") or {}).items():
                    disk_usage_gauge.labels(host=host, mount=mount).set(pct)
                network_in_gauge.labels(host=host, interface="eth0").set(m["network_in"])
                network_out_gauge.labels(host=host, interface="eth0").set(m["network_out"])
                uptime_gauge.labels(host=host).set(m["uptime"])

                check_alerts(node_id, m)

                # rolling 60-point history
                metrics_history[node_id].append({
                    "timestamp": datetime.utcnow().isoformat(),
                    **m,
                })
                if len(metrics_history[node_id]) > 60:
                    metrics_history[node_id].pop(0)

            except Exception as exc:
                logger.error("Collection error for %s: %s", node_id, exc)

        time.sleep(15)

def _node_status(m: dict) -> str:
    if m["cpu"] >= THRESHOLDS["cpu"]["critical"] or m["memory"] >= THRESHOLDS["memory"]["critical"]:
        return "critical"
    if m["cpu"] >= THRESHOLDS["cpu"]["warning"] or m["memory"] >= THRESHOLDS["memory"]["warning"]:
        return "warning"
    return "healthy"

# start background thread
_thread = threading.Thread(target=_collection_loop, daemon=True)
_thread.start()

# ── Routes ────────────────────────────────────────────────────────────────────

@app.before_request
def _before():
    request._start_time = time.time()

@app.after_request
def _after(response):
    elapsed = time.time() - getattr(request, "_start_time", time.time())
    http_requests_total.labels(
        method=request.method,
        endpoint=request.endpoint or "unknown",
        status=response.status_code,
    ).inc()
    response_time_hist.labels(endpoint=request.endpoint or "unknown").observe(elapsed)
    return response

@app.route("/")
def dashboard():
    return render_template("dashboard.html")

@app.route("/api/nodes")
def api_nodes():
    return jsonify(list(nodes.values()))

@app.route("/api/nodes/<node_id>")
def api_node(node_id: str):
    if node_id not in nodes:
        return jsonify({"error": "Node not found"}), 404
    return jsonify({**nodes[node_id], "history": metrics_history.get(node_id, [])})

@app.route("/api/alerts")
def api_alerts():
    return jsonify(alerts)

@app.route("/api/alerts/<alert_id>/acknowledge", methods=["POST"])
def ack_alert(alert_id: str):
    for a in alerts:
        if a["id"] == alert_id:
            a["acknowledged"] = True
            a["ack_time"]     = datetime.utcnow().isoformat()
            return jsonify({"status": "acknowledged", "alert": a})
    return jsonify({"error": "Alert not found"}), 404

@app.route("/api/alerts/history")
def api_alert_history():
    return jsonify(alert_history[-100:])

@app.route("/api/summary")
def api_summary():
    total   = len(nodes)
    healthy  = sum(1 for n in nodes.values() if n["status"] == "healthy")
    warning  = sum(1 for n in nodes.values() if n["status"] == "warning")
    critical = sum(1 for n in nodes.values() if n["status"] == "critical")
    avg_cpu  = round(sum(n["metrics"].get("cpu", 0) for n in nodes.values()) / max(total, 1), 1)
    avg_mem  = round(sum(n["metrics"].get("memory", 0) for n in nodes.values()) / max(total, 1), 1)
    return jsonify({
        "nodes": {"total": total, "healthy": healthy, "warning": warning, "critical": critical},
        "alerts": {
            "total":    len(alerts),
            "critical": sum(1 for a in alerts if a["severity"] == "critical"),
            "warning":  sum(1 for a in alerts if a["severity"] == "warning"),
            "unacked":  sum(1 for a in alerts if not a["acknowledged"]),
        },
        "avg_cpu":    avg_cpu,
        "avg_memory": avg_mem,
        "uptime":     round(time.time() - START_TIME),
    })

@app.route("/api/thresholds", methods=["GET"])
def get_thresholds():
    return jsonify(THRESHOLDS)

@app.route("/api/thresholds", methods=["PUT"])
def update_thresholds():
    data = request.get_json(force=True)
    for metric, vals in data.items():
        if metric in THRESHOLDS:
            THRESHOLDS[metric].update(vals)
    return jsonify({"status": "updated", "thresholds": THRESHOLDS})

@app.route("/metrics")
def prometheus_metrics():
    return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "uptime": round(time.time() - START_TIME)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
