# Deployment Guide

## Table of Contents

1. [Docker Deployment](#docker-deployment)
2. [Docker Compose Setup](#docker-compose-setup)
3. [Environment Configuration](#environment-configuration)
4. [MongoDB Setup](#mongodb-setup)
5. [Production Checklist](#production-checklist)
6. [Scaling Considerations](#scaling-considerations)
7. [Health Monitoring](#health-monitoring)

---

## Docker Deployment

### Building the Image

```bash
docker build -t q-guardian:latest -f docker/Dockerfile .
```

The Dockerfile uses Python 3.12-slim as the base image, installs dependencies, runs as a non-root user, and configures a health check.

### Running the Container

```bash
docker run -d \
  --name q-guardian \
  -p 8000:8000 \
  -e APP_ENVIRONMENT=production \
  -e APP_DEBUG=false \
  -e APP_LOG_LEVEL=INFO \
  -e SECRET_KEY=your-production-secret-key \
  -e MONGODB_URL=mongodb://mongo:27017 \
  q-guardian:latest
```

### Verifying the Container

```bash
# Check container status
docker ps

# View logs
docker logs q-guardian

# Health check
curl http://localhost:8000/api/v1/health
```

### Custom Dockerfile

If you need to extend the base image:

```dockerfile
FROM q-guardian:latest

# Add custom plugins
COPY my-plugins/ /app/plugins/

# Add custom configuration
COPY config.json /app/config.json

# Install additional dependencies
USER root
RUN pip install my-custom-package
USER appuser

CMD ["uvicorn", "src.q_guardian.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Docker Compose Setup

### Basic Compose File

```yaml
version: "3.8"

services:
  q-guardian:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - APP_ENVIRONMENT=production
      - APP_DEBUG=false
      - APP_LOG_LEVEL=INFO
      - SECRET_KEY=${SECRET_KEY}
      - MONGODB_URL=mongodb://mongo:27017
      - MONGODB_DATABASE=q_guardian
      - CORS_ORIGINS=["https://your-app.com"]
    depends_on:
      mongo:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/api/v1/health').raise_for_status()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  mongo:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db
    environment:
      - MONGO_INITDB_ROOT_USERNAME=${MONGO_USER:-admin}
      - MONGO_INITDB_ROOT_PASSWORD=${MONGO_PASSWORD:-password}
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

volumes:
  mongo_data:
```

### Starting the Stack

```bash
# Create .env file
cat > .env << EOF
SECRET_KEY=$(openssl rand -hex 32)
MONGO_USER=admin
MONGO_PASSWORD=$(openssl rand -hex 16)
EOF

# Build and start
docker compose up -d --build

# View logs
docker compose logs -f q-guardian
```

### Stopping the Stack

```bash
docker compose down

# Remove volumes (destroys data)
docker compose down -v
```

---

## Environment Configuration

### Application Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | Q-Guardian | Application name |
| `APP_ENVIRONMENT` | development | Environment (development, testing, production) |
| `APP_DEBUG` | true | Enable debug mode |
| `APP_HOST` | 0.0.0.0 | Server bind host |
| `APP_PORT` | 8000 | Server port |
| `APP_LOG_LEVEL` | INFO | Logging level |
| `APP_LOG_DIR` | logs | Log file directory |

### Database Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URL` | mongodb://localhost:27017 | MongoDB connection URL |
| `MONGODB_DATABASE` | q_guardian | Database name |
| `MONGODB_MIN_POOL_SIZE` | 1 | Minimum connection pool |
| `MONGODB_MAX_POOL_SIZE` | 10 | Maximum connection pool |
| `MONGODB_TIMEOUT_MS` | 5000 | Connection timeout (ms) |

### Security Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | change-me... | Application secret key |
| `JWT_ALGORITHM` | HS256 | JWT signing algorithm |
| `JWT_EXPIRATION_MINUTES` | 30 | JWT token lifetime |
| `JWT_REFRESH_EXPIRATION_DAYS` | 7 | Refresh token lifetime |

### CORS Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | localhost:3000,8080 | Allowed origins |
| `CORS_ALLOW_CREDENTIALS` | true | Allow credentials |
| `CORS_ALLOW_METHODS` | * | Allowed HTTP methods |
| `CORS_ALLOW_HEADERS` | * | Allowed headers |

### Production Environment File

```bash
# .env.production
APP_ENVIRONMENT=production
APP_DEBUG=false
APP_LOG_LEVEL=WARNING
APP_LOG_FORMAT=json
APP_HOST=0.0.0.0
APP_PORT=8000

SECRET_KEY=<generate-with-openssl-rand-hex-32>
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=15

MONGODB_URL=mongodb://user:password@mongo-host:27017/?authSource=admin
MONGODB_DATABASE=q_guardian_production
MONGODB_MIN_POOL_SIZE=5
MONGODB_MAX_POOL_SIZE=50

CORS_ORIGINS=["https://app.yourdomain.com"]
LOG_LEVEL=WARNING
LOG_FORMAT=json
```

---

## MongoDB Setup

### Local Development

```bash
# Start MongoDB
mongod --dbpath /data/db --port 27017

# Or with Docker
docker run -d -p 27017:27017 --name mongo mongo:7
```

### Production Replica Set

```yaml
# docker-compose.prod.yml
services:
  mongo:
    image: mongo:7
    command: mongod --replSet rs0 --bind_ip_all
    volumes:
      - mongo_data:/data/db
    ports:
      - "27017:27017"

  mongo-init:
    image: mongo:7
    depends_on:
      - mongo
    command: >
      mongosh --host mongo:27017 --eval '
        rs.initiate({
          _id: "rs0",
          members: [{ _id: 0, host: "mongo:27017" }]
        })
      '
```

### Connection URL Formats

```
# Local
mongodb://localhost:27017

# Authenticated
mongodb://user:password@localhost:27017/?authSource=admin

# Replica Set
mongodb://user:password@host1:27017,host2:27017,host3:27017/?replicaSet=rs0&authSource=admin

# Atlas
mongodb+srv://user:password@cluster.xxxxx.mongodb.net/q_guardian?retryWrites=true&w=majority
```

---

## Production Checklist

### Security

- [ ] Change `SECRET_KEY` from default value
- [ ] Set `APP_DEBUG=false`
- [ ] Set `APP_ENVIRONMENT=production`
- [ ] Configure `CORS_ORIGINS` for your domain only
- [ ] Enable HTTPS (via reverse proxy)
- [ ] Set restrictive `APP_LOG_LEVEL` (WARNING or ERROR)
- [ ] Use authenticated MongoDB connection
- [ ] Run container as non-root user (already configured in Dockerfile)

### Performance

- [ ] Set `APP_LOG_FORMAT=json` for structured logging
- [ ] Configure MongoDB connection pool sizes
- [ ] Set appropriate `request_timeout_seconds`
- [ ] Enable `enable_caching` in production
- [ ] Configure log rotation (`LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`)

### Reliability

- [ ] Configure health check endpoint for load balancer
- [ ] Set `restart: unless-stopped` in Docker Compose
- [ ] Configure MongoDB replica set for high availability
- [ ] Set up log aggregation
- [ ] Configure alerting for error rates

### Monitoring

- [ ] Register `ObservabilityPlugin` for metrics and tracing
- [ ] Configure Prometheus/Grafana for dashboards
- [ ] Set up alerts for anomaly thresholds
- [ ] Monitor database connection pool usage
- [ ] Track plugin health status

---

## Scaling Considerations

### Horizontal Scaling

Run multiple Q-Guardian instances behind a load balancer:

```
                    +--> q-guardian-1
Load Balancer ----->+--> q-guardian-2
                    +--> q-guardian-3
```

All instances share the same MongoDB backend. The event bus is per-process; use external message queues for cross-process event distribution if needed.

### Vertical Scaling

Key resource limits to tune:

```yaml
environment:
  - APP_PORT=8000
  - MONGODB_MIN_POOL_SIZE=10
  - MONGODB_MAX_POOL_SIZE=100
```

### Resource Limits

```yaml
deploy:
  resources:
    limits:
      cpus: "2.0"
      memory: 4G
    reservations:
      cpus: "0.5"
      memory: 1G
```

### Caching

Enable framework-level caching to reduce redundant processing:

```python
config = FrameworkConfig(
    runtime={"enable_caching": True}
)
```

---

## Health Monitoring

### Health Endpoint

```bash
curl http://localhost:8000/api/v1/health
```

Response:

```json
{
  "status": "healthy",
  "application": "Q-Guardian",
  "version": "1.1.0",
  "environment": "production",
  "timestamp": "2026-07-19T12:00:00Z",
  "database": {
    "status": "healthy",
    "latency_ms": 2
  }
}
```

### Kubernetes Health Probes

```yaml
livenessProbe:
  httpGet:
    path: /api/v1/health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /api/v1/health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3
```

### Version Endpoint

```bash
curl http://localhost:8000/api/v1/version
```

### Status Endpoint

```bash
curl http://localhost:8000/api/v1/status
```

### Plugin Health Check

```python
import asyncio
import httpx

async def check_health():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/api/v1/health")
        data = response.json()
        print(f"Status: {data['status']}")
        return data["status"] == "healthy"

asyncio.run(check_health())
```
