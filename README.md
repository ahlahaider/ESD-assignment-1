```markdown
# Ticket Booking Observability Project

A small FastAPI ticket booking service instrumented end-to-end with:

- Prometheus + Grafana metrics monitoring
- Filebeat → Elasticsearch → Kibana structured logging pipeline
- Node Exporter infrastructure monitoring

Built for the **Enterprise Software Development Assignment 1 (Observability)**.

---

# What this project is

This project implements a minimal event ticket booking API designed to demonstrate observability concepts.

The system demonstrates:

- Application metrics collection
- Structured JSON logging
- Monitoring dashboards
- Log searching and request tracing
- Fault injection experiments
- Infrastructure monitoring

This is **not a production booking system**. Booking information is stored only in application memory and resets whenever the application restarts.

---

# Project Structure

```

ticket-observability/
│
├── main.py
├── docker-compose.yml
├── requirements.txt
├── README.md
│
└── telemetry/
├── prometheus/
│   └── prometheus.yml
│
├── grafana/
│   └── provisioning/
│
└── filebeat/
└── filebeat.yml

````

---

# Prerequisites

Install the following before running:

- Docker Desktop
- Docker Compose v2

Verify Docker Compose:

```bash
docker compose version
````

Recommended Docker resources:

* Minimum 4 GB RAM allocated to Docker
* Approximately 4 GB free disk space

(Elasticsearch is the heaviest component.)

---

# How to Start the Stack

From the project root:

```bash
docker compose up -d --build
```

The first run downloads all required images and may take several minutes.

Check running containers:

```bash
docker compose ps
```

Expected containers:

```
ticket-app
prometheus
grafana
node-exporter
elasticsearch
filebeat
kibana
```

All containers should show status as `Up`.

---

# Architecture Overview

## Metrics Pipeline

```
ticket-app
     |
     | /metrics endpoint
     ↓
Prometheus
     |
     | PromQL queries
     ↓
Grafana
```

Flow:

* The FastAPI application exposes metrics through `/metrics`
* Prometheus periodically scrapes application metrics
* Grafana visualizes application and infrastructure metrics

## Logging Pipeline

```
ticket-app
     |
     | Structured JSON logs
     ↓
Docker stdout logs
     |
     ↓
Filebeat
     |
     ↓
Elasticsearch
     |
     ↓
Kibana
```

Flow:

* Application logs are generated as JSON logs
* Docker captures container stdout logs
* Filebeat collects and forwards logs
* Elasticsearch stores searchable documents
* Kibana provides log search and analysis

---

# Accessing Services

| Service               | URL                                                      | Purpose                    |
| --------------------- | -------------------------------------------------------- | -------------------------- |
| Ticket App Swagger UI | [http://localhost:8000/docs](http://localhost:8000/docs) | Test API endpoints         |
| Prometheus            | [http://localhost:9090](http://localhost:9090)           | Metrics and PromQL queries |
| Grafana               | [http://localhost:3000](http://localhost:3000)           | Monitoring dashboard       |
| Kibana                | [http://localhost:5601](http://localhost:5601)           | Log search and analysis    |
| Elasticsearch         | [http://localhost:9200](http://localhost:9200)           | Elasticsearch API          |

---

# Grafana Login

```
Username: admin
Password: admin
```

Dashboard:

```
Ticket Booking War Room
```

---

# Kibana Setup

Open:

```
Kibana → Discover
```

Select data view:

```
filebeat-*
```

---

# Application Endpoints

| Method | Endpoint                       | Purpose                                |
| ------ | ------------------------------ | -------------------------------------- |
| GET    | `/events`                      | List events and available seats        |
| POST   | `/book?event_id=&seats=`       | Book tickets                           |
| POST   | `/cancel/{booking_id}`         | Cancel booking                         |
| GET    | `/health`                      | Health check endpoint                  |
| GET    | `/metrics`                     | Prometheus metrics endpoint            |
| POST   | `/chaos/delay?enabled=&delay=` | Enable/disable slow request simulation |
| POST   | `/chaos/cardinality?enabled=`  | Enable/disable cardinality experiment  |

---

# Example Usage

## View events

```bash
curl http://localhost:8000/events
```

---

## Book tickets

Example: Book 2 seats for event 1

```bash
curl -X POST "http://localhost:8000/book?event_id=1&seats=2"
```

---

## Cancel booking

```bash
curl -X POST http://localhost:8000/cancel/1
```

---

# Testing the Observability Setup

## Check Prometheus Targets

Open:

```
http://localhost:9090/targets
```

Expected:

```
ticket-app       UP
node-exporter    UP
```

---

## Check Application Metrics

```bash
curl http://localhost:8000/metrics | grep tickets_booked_total
```

---

## Check Logs in Kibana

Open:

```
Kibana → Discover
```

Search:

```
message : "Ticket booking successful"
```

For request tracing:

```
request_id : "<uuid>"
```

---

# Fault Injection Experiments

## Experiment 1: Slow Requests

Enable artificial delay:

```bash
curl -X POST "http://localhost:8000/chaos/delay?enabled=true&delay=0.5"
```

This introduces a 500ms delay on 20% of booking requests.

Disable delay:

```bash
curl -X POST "http://localhost:8000/chaos/delay?enabled=false"
```

---

## Experiment 2: Cardinality Explosion

Enable high-cardinality metric generation:

```bash
curl -X POST "http://localhost:8000/chaos/cardinality?enabled=true"
```

Disable:

```bash
curl -X POST "http://localhost:8000/chaos/cardinality?enabled=false"
```

---

# Cleaning Up

## Stop containers and keep data

```bash
docker compose stop
```

---

## Remove containers but keep volumes

Elasticsearch data remains:

```bash
docker compose down
```

---

## Complete Reset

Deletes containers, volumes, logs, and stored data:

```bash
docker compose down -v
```

---

# Troubleshooting

If application code or configuration changes are made:

```bash
docker compose down
docker compose up -d --build
```

For a complete fresh reset:

```bash
docker compose down -v
docker compose up -d --build
```


