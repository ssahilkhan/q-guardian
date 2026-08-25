# Operations Guide

## Table of Contents

1. [Monitoring Setup](#monitoring-setup)
2. [Alerting Configuration](#alerting-configuration)
3. [Log Management](#log-management)
4. [Performance Tuning](#performance-tuning)
5. [Capacity Planning](#capacity-planning)
6. [Incident Response](#incident-response)
7. [Backup and Recovery](#backup-and-recovery)

---

## Monitoring Setup

### Observability Plugin

Enable full observability by registering the `ObservabilityPlugin`:

```python
from q_guardian.observability import ObservabilityPlugin

plugin = ObservabilityPlugin(
    config={
        "metrics": {"enabled": True, "interval_seconds": 15},
        "tracing": {"enabled": True, "sample_rate": 0.1},
        "health": {"enabled": True, "check_interval_seconds": 30},
        "analytics": {"enabled": True},
        "alerts": {"enabled": True},
    }
)

guardian = Guardian()
guardian.register_plugin(plugin)
await guardian.start()
```

### Prometheus Integration

Q-Guardian exports metrics via a Prometheus-compatible endpoint:

```python
from q_guardian.observability.integrations.prometheus import PrometheusExporter

exporter = PrometheusExporter(port=9090)
exporter.start()
```

Key metrics exported:

- `qguardian_scans_total` -- total prompt scans
- `qguardian_threats_detected_total` -- total threats detected
- `qguardian_scan_duration_seconds` -- scan latency histogram
- `qguardian_active_sessions` -- current active sessions
- `qguardian_plugin_health` -- plugin health status
- `qguardian_ml_inference_duration_seconds` -- ML inference latency

### Grafana Dashboard

Import the Q-Guardian Grafana dashboard:

```python
from q_guardian.observability.integrations.grafana import GrafanaExporter

exporter = GrafanaExporter(dashboard_url="http://grafana:3000")
```

Pre-built dashboards include:

- Framework Overview (scan rate, threat rate, latency)
- Plugin Health (per-plugin status and performance)
- ML Model Performance (accuracy, inference time)
- Quantum Backend Status (circuit depth, execution time)

### Datadog Integration

```python
from q_guardian.observability.integrations.datadog import DatadogExporter

exporter = DatadogExporter(api_key="your-api-key", app_key="your-app-key")
```

---

## Alerting Configuration

### Alert Rules

Define alert thresholds:

```python
from q_guardian.observability.alerts.alert_engine import AlertEngine

alert_config = {
    "rules": [
        {
            "name": "high_threat_rate",
            "metric": "qguardian_threats_detected_total",
            "condition": "rate > 10 per minute",
            "severity": "critical",
            "message": "Threat detection rate exceeded threshold",
        },
        {
            "name": "high_latency",
            "metric": "qguardian_scan_duration_seconds",
            "condition": "p95 > 5.0",
            "severity": "warning",
            "message": "Scan latency exceeds 5 seconds at p95",
        },
        {
            "name": "plugin_failure",
            "metric": "qguardian_plugin_health",
            "condition": "status == 'error'",
            "severity": "critical",
            "message": "Plugin has entered error state",
        },
        {
            "name": "ml_model_drift",
            "metric": "qguardian_ml_accuracy",
            "condition": "value < 0.85",
            "severity": "warning",
            "message": "ML model accuracy dropped below 85%",
        },
    ]
}
```

### Alert Destinations

Configure where alerts are sent:

```python
alert_config["destinations"] = {
    "slack": {
        "webhook_url": "https://hooks.slack.com/...",
        "channel": "#q-guardian-alerts",
    },
    "email": {
        "smtp_host": "smtp.example.com",
        "from": "alerts@qguardian.example.com",
        "to": ["ops-team@example.com"],
    },
    "pagerduty": {
        "routing_key": "your-routing-key",
    },
}
```

### Alert Lifecycle

```
Metric exceeds threshold
    |
    v
Alert triggered (AlertTriggered event published)
    |
    +-- Notify Slack
    +-- Send email
    +-- Page on-call
    |
    v
Metric returns to normal
    |
    v
Alert resolved
```

---

## Log Management

### Log Configuration

```python
from q_guardian.logging.config import setup_logging

setup_logging(
    log_level="INFO",
    log_dir="logs",
    log_format="json",
)
```

### Log Format (JSON)

```json
{
  "timestamp": "2026-07-19T12:00:00Z",
  "event": "prompt_scanned",
  "level": "info",
  "logger": "security.prompt_scanner",
  "plugin": "prompt-scanner",
  "decision": "block",
  "risk_score": 0.85,
  "findings_count": 3,
  "processing_time_ms": 12.5,
  "correlation_id": "req-abc-123"
}
```

### Log Levels

| Level | Use Case |
|-------|----------|
| DEBUG | Detailed diagnostic information |
| INFO | Normal operational events |
| WARNING | Unexpected but handled conditions |
| ERROR | Failed operations requiring attention |
| CRITICAL | System-level failures |

### Log Rotation

Configure automatic log rotation:

```bash
# Environment variables
LOG_MAX_BYTES=10485760    # 10MB per file
LOG_BACKUP_COUNT=30       # Keep 30 backup files
```

### Centralized Logging

Send structured logs to external systems:

```python
import structlog

# Add context processor for centralized logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
```

Compatible with:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Fluentd / Fluent Bit
- AWS CloudWatch Logs
- Google Cloud Logging
- Azure Monitor

---

## Performance Tuning

### Scan Latency

Typical scan latency targets:

| Pipeline | Target Latency |
|----------|---------------|
| Rules only | < 5ms |
| Rules + ML | < 50ms |
| Rules + ML + Quantum | < 500ms |

### Configuration Tuning

```python
config = FrameworkConfig(
    runtime={
        "max_concurrent_agents": 200,  # Increase for high concurrency
        "request_timeout_seconds": 10,  # Reduce for faster failure
        "enable_caching": True,  # Enable result caching
    },
    prompt_scanner={
        "enabled": True,
        "sensitivity": "medium",  # "low" is faster, "high" is thorough
    },
)
```

### MongoDB Performance

- Use connection pooling (set `MONGODB_MIN_POOL_SIZE` and `MONGODB_MAX_POOL_SIZE`)
- Create indexes for frequently queried fields
- Monitor slow queries with MongoDB profiler
- Use read replicas for read-heavy workloads

### ML Model Performance

- Pre-load models at startup to avoid cold-start latency
- Use batch inference for bulk scanning
- Cache feature extraction results
- Consider model quantization for reduced inference time

### Memory Management

Monitor memory usage:

```python
import psutil
import os

process = psutil.Process(os.getpid())
memory_mb = process.memory_info().rss / 1024 / 1024
print(f"Memory usage: {memory_mb:.1f} MB")
```

---

## Capacity Planning

### Key Metrics to Monitor

| Metric | Warning Threshold | Critical Threshold |
|--------|-------------------|--------------------|
| Scan rate | > 100/sec | > 500/sec |
| Active sessions | > 500 | > 1000 |
| Memory usage | > 70% | > 90% |
| CPU usage | > 70% | > 90% |
| MongoDB connections | > 80% pool | > 95% pool |
| Plugin error rate | > 1% | > 5% |

### Sizing Guidelines

| Component | Small (Dev) | Medium (Staging) | Large (Production) |
|-----------|-------------|-------------------|---------------------|
| Instances | 1 | 2-3 | 5+ |
| CPU | 1 core | 2 cores | 4+ cores |
| Memory | 512MB | 2GB | 4+ GB |
| MongoDB | Single | Replica set | Sharded cluster |

### Scaling Triggers

Consider scaling when:
- Scan latency consistently exceeds targets
- Plugin error rate increases
- Memory usage remains above 70%
- MongoDB connection pool is near capacity
- Threat detection rate exceeds normal operational bounds

---

## Incident Response

### Severity Levels

| Level | Description | Response Time |
|-------|-------------|---------------|
| P0 - Critical | System down, data loss risk | Immediate |
| P1 - High | Major feature degraded | 1 hour |
| P2 - Medium | Minor feature issue | 4 hours |
| P3 - Low | Cosmetic or documentation | Next business day |

### Incident Playbook

**System Unresponsive:**

1. Check health endpoint: `curl http://localhost:8000/api/v1/health`
2. Check container status: `docker ps`
3. Review recent logs: `docker logs --tail 100 q-guardian`
4. Restart container: `docker restart q-guardian`
5. If persists, check MongoDB connectivity

**High Threat Detection Rate:**

1. Check if rate is from a specific source IP
2. Review recent threats in observability dashboard
3. Consider temporarily increasing sensitivity
4. If attack, enable additional blocking rules
5. Document and report

**ML Model Accuracy Drop:**

1. Check training data quality
2. Review recent model changes
3. Roll back to previous model version
4. Retrain with fresh data
5. Deploy updated model

### Communication Template

```
Incident: [Brief description]
Severity: P0/P1/P2/P3
Start Time: [Timestamp]
Impact: [Description of user impact]
Status: Investigating / Identified / Monitoring / Resolved
Next Update: [Time]
```

---

## Backup and Recovery

### MongoDB Backup

```bash
# Manual backup
mongodump --uri="mongodb://localhost:27017" --db=q_guardian --out=/backup/$(date +%Y%m%d)

# Automated backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
mongodump --uri="$MONGODB_URL" --db=q_guardian --out=/backups/$DATE
tar -czf /backups/q_guardian_$DATE.tar.gz /backups/$DATE
find /backups -mtime +30 -delete
```

### Backup Schedule

| Backup Type | Frequency | Retention |
|-------------|-----------|-----------|
| Full dump | Daily | 30 days |
| Incremental | Hourly | 7 days |
| Config backup | On change | 90 days |

### Recovery Procedure

```bash
# Stop the application
docker compose stop q-guardian

# Restore MongoDB
mongorestore --uri="mongodb://localhost:27017" --db=q_guardian /backups/20260719

# Verify data integrity
mongosh --eval "db.adminCommand('dbStats')"

# Restart application
docker compose start q-guardian

# Verify health
curl http://localhost:8000/api/v1/health
```

### Configuration Backup

```bash
# Back up all configuration
tar -czf config_backup_$(date +%Y%m%d).tar.gz \
    .env \
    .env.production \
    docker-compose.yml \
    config.json
```

### Disaster Recovery

For full disaster recovery:

1. Provision new infrastructure
2. Restore MongoDB from latest backup
3. Deploy Q-Guardian containers
4. Configure environment variables
5. Verify health and connectivity
6. Update DNS/load balancer to point to new instances
7. Run smoke tests
