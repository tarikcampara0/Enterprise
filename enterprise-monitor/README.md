# NetWatch Enterprise — Monitoring & Alerting System

> A production-grade infrastructure monitoring platform built with Python/Flask, Prometheus, Grafana, Docker, and AWS — mirroring what real DevOps and IT operations teams use in enterprise environments.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     AWS EC2 / Docker Host                       │
│                                                                 │
│  ┌──────────┐    ┌────────────┐    ┌─────────────────────────┐ │
│  │  Nginx   │───▶│ Flask App  │───▶│  Prometheus Client Lib  │ │
│  │  :80     │    │  :5000     │    │  (metrics endpoint)     │ │
│  └──────────┘    └─────┬──────┘    └─────────────────────────┘ │
│                        │                                        │
│                  ┌─────▼──────┐    ┌────────────────────────┐  │
│                  │ Prometheus │◀───│   Node Exporter :9100  │  │
│                  │  :9090     │◀───│   cAdvisor      :8080  │  │
│                  └─────┬──────┘    └────────────────────────┘  │
│                        │                                        │
│              ┌─────────▼──────────┐                            │
│              │   Alertmanager     │──▶ Email / Slack / PagerDuty│
│              │      :9093         │                            │
│              └────────────────────┘                            │
│                                                                 │
│              ┌────────────────────┐                            │
│              │      Grafana       │                            │
│              │       :3000        │                            │
│              └────────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12, Flask 3.0, Gunicorn |
| Metrics collection | Prometheus + prometheus-client |
| Host metrics | Node Exporter |
| Container metrics | cAdvisor |
| Visualization | Grafana 10 |
| Alert routing | Alertmanager |
| Reverse proxy | Nginx |
| Containerization | Docker + Docker Compose |
| Cloud deployment | AWS EC2, Terraform |
| Testing | pytest |

---

## Features

- **Real-time dashboard** — live CPU, memory, disk, network metrics across 7 simulated infrastructure nodes (web servers, databases, cache, load balancer)
- **Threshold-based alerting** — configurable warning/critical thresholds per metric, deduplication, acknowledgement
- **Prometheus metrics** — full `/metrics` endpoint scraped by Prometheus every 15 s
- **Grafana dashboards** — auto-provisioned datasource and overview dashboard
- **Alertmanager routing** — severity-based routing to email and Slack, with inhibition rules
- **Prometheus alert rules** — 10+ production-quality alerting rules covering CPU, memory, disk, network, error rates, latency
- **Docker Compose** — single command to spin up the full 7-container stack
- **AWS Terraform** — one-command cloud deployment with VPC, security groups, IAM, CloudWatch
- **Nginx reverse proxy** — rate limiting, security headers, Grafana proxying
- **Test suite** — unit + integration tests covering API, alert logic, and node status

---

## Quick Start (Local)

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/install/) ≥ 2.20

### 1. Clone & configure

```bash
git clone https://github.com/YOUR_USERNAME/enterprise-monitor.git
cd enterprise-monitor
cp .env.example .env
# Edit .env — at minimum change SECRET_KEY and GRAFANA_PASSWORD
```

### 2. Launch the full stack

```bash
./scripts/deploy.sh local
# or manually:
docker-compose up -d --build
```

### 3. Open the interfaces

| Service | URL | Credentials |
|---|---|---|
| **NetWatch Dashboard** | http://localhost:5000 | — |
| **Prometheus** | http://localhost:9090 | — |
| **Grafana** | http://localhost:3000 | admin / see `.env` |
| **Alertmanager** | http://localhost:9093 | — |
| **Nginx (proxy)** | http://localhost:80 | — |

### 4. Verify everything is healthy

```bash
# Check all containers are running
docker-compose ps

# Tail logs
docker-compose logs -f app

# Hit the health endpoint
curl http://localhost:5000/health
```

---

## API Reference

All endpoints return JSON.

### `GET /api/nodes`
Returns all monitored nodes with current metrics and status.

```json
[
  {
    "id": "web-01",
    "name": "Web Server 01",
    "type": "web",
    "ip": "10.0.1.10",
    "status": "healthy",
    "last_seen": "2024-11-15T10:23:01.123456",
    "metrics": {
      "cpu": 34.2,
      "memory": 47.8,
      "disk": { "/": 43.1 },
      "network_in": 5240000,
      "network_out": 3120000,
      "uptime": 86400
    }
  }
]
```

### `GET /api/nodes/<id>`
Returns a single node with rolling 60-point metric history.

### `GET /api/alerts`
Returns all currently active alerts.

```json
[
  {
    "id": "web-01_cpu",
    "node_id": "web-01",
    "node_name": "Web Server 01",
    "metric": "cpu",
    "label": "CPU usage",
    "value": 93.4,
    "threshold": 90,
    "severity": "critical",
    "timestamp": "2024-11-15T10:23:01.123456",
    "message": "CPU usage on Web Server 01 is 93.4% (threshold: 90%)",
    "acknowledged": false
  }
]
```

### `POST /api/alerts/<id>/acknowledge`
Acknowledges an alert, suppressing repeat notifications.

### `GET /api/alerts/history`
Returns the last 100 alerts (including resolved).

### `GET /api/summary`
Returns aggregate cluster health summary.

### `GET /api/thresholds` · `PUT /api/thresholds`
Get or update alert thresholds at runtime.

```bash
# Example: lower CPU warning threshold
curl -X PUT http://localhost:5000/api/thresholds \
  -H "Content-Type: application/json" \
  -d '{"cpu": {"warning": 65, "critical": 85}}'
```

### `GET /metrics`
Prometheus-format metrics endpoint (scraped every 15 s).

---

## Alert Thresholds

Default thresholds (configurable via API or `THRESHOLDS` dict in `app/main.py`):

| Metric | Warning | Critical |
|---|---|---|
| CPU | 70% | 90% |
| Memory | 75% | 90% |
| Disk | 80% | 95% |
| Network In | 80 MB/s | 95 MB/s |
| Network Out | 80 MB/s | 95 MB/s |

---

## Deploying to AWS

### Prerequisites

- [Terraform](https://www.terraform.io/downloads) ≥ 1.7
- AWS CLI configured (`aws configure`)
- An EC2 key pair in your target region

### 1. Provision infrastructure

```bash
cd terraform

# Create a terraform.tfvars file:
cat > terraform.tfvars <<EOF
aws_region    = "us-east-1"
instance_type = "t3.medium"
key_name      = "your-key-pair-name"
allowed_cidr  = "YOUR_IP/32"
EOF

terraform init
terraform plan
terraform apply
```

Terraform will output the server IP and URLs.

### 2. Deploy application code

```bash
# Sync code and start services on EC2
./scripts/deploy.sh aws
```

### 3. Access

```bash
# SSH in
ssh -i ~/.ssh/your-key.pem ubuntu@<EC2_IP>

# View logs on server
docker-compose -f /opt/netwatch/docker-compose.yml logs -f
```

---

## Configuring Notifications

### Slack

1. Create an [Incoming Webhook](https://api.slack.com/messaging/webhooks) in your Slack workspace
2. Add the URL to `alertmanager/alertmanager.yml`:

```yaml
global:
  slack_api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'
```

### Email (Gmail example)

1. Enable 2FA on your Google account
2. Generate an [App Password](https://myaccount.google.com/apppasswords)
3. Update `alertmanager/alertmanager.yml`:

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@your-domain.com'
  smtp_auth_username: 'alerts@your-domain.com'
  smtp_auth_password: 'your-16-char-app-password'
```

After editing, reload Alertmanager:

```bash
curl -X POST http://localhost:9093/-/reload
```

---

## Running Tests

```bash
# Install test dependencies
pip install pytest flask prometheus-client psutil

# Run the full suite
cd enterprise-monitor
pytest tests/ -v

# Run with coverage
pip install pytest-cov
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## Project Structure

```
enterprise-monitor/
├── app/
│   ├── main.py                  # Flask app, metrics, alert engine, API
│   ├── templates/
│   │   └── dashboard.html       # Real-time dashboard UI
│   ├── requirements.txt
│   └── Dockerfile
├── prometheus/
│   ├── prometheus.yml           # Scrape configs
│   └── alert_rules.yml          # 10+ alerting rules
├── alertmanager/
│   └── alertmanager.yml         # Routing, receivers (email + Slack)
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── prometheus.yml   # Auto-provisioned Prometheus datasource
│       └── dashboards/
│           ├── dashboard.yml
│           └── netwatch_overview.json
├── nginx/
│   └── nginx.conf               # Reverse proxy + rate limiting
├── terraform/
│   └── main.tf                  # AWS VPC, EC2, SGs, IAM, CloudWatch
├── scripts/
│   ├── deploy.sh                # Local + AWS deployment automation
│   └── user_data.sh             # EC2 bootstrap script
├── tests/
│   └── test_app.py              # pytest suite
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Simulated Infrastructure

The system simulates a realistic enterprise environment with 7 nodes:

| Node | Type | Simulated Role |
|---|---|---|
| web-01 | Web | Application server (35% avg CPU) |
| web-02 | Web | Application server (35% avg CPU) |
| db-01 | Database | Primary DB (55% avg CPU, 70% mem) |
| db-02 | Database | Read replica |
| cache-01 | Cache | Redis (20% CPU, 85% mem) |
| lb-01 | Network | Load balancer (15% CPU) |
| monitor | Monitor | Real host metrics via psutil |

Metrics use a Gaussian random-walk algorithm so values drift realistically rather than jumping randomly. A 2% chance of CPU spike per collection cycle simulates real incidents.

---

## Production Hardening Checklist

Before exposing to the internet:

- [ ] Change all default passwords in `.env`
- [ ] Restrict Prometheus/Alertmanager ports to internal network only (Nginx `allow`/`deny`)
- [ ] Enable TLS (add cert to Nginx, set `GF_SERVER_PROTOCOL=https` in Grafana)
- [ ] Set `FLASK_ENV=production` (already default in Dockerfile)
- [ ] Store secrets in AWS Secrets Manager or HashiCorp Vault, not `.env`
- [ ] Enable CloudWatch log groups for Docker container logs
- [ ] Set up S3 remote state for Terraform
- [ ] Restrict EC2 security group SSH to a bastion host

---

## License

MIT — see [LICENSE](LICENSE)
