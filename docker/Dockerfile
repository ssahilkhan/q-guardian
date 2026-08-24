FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (pinned layer for build caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code + package metadata
COPY pyproject.toml .
COPY README.md .
COPY src/ src/
# Install the package itself (--no-deps: versions come from pinned requirements.txt)
RUN pip install --no-cache-dir --no-deps .

# Non-root user; app persists models/policies/responses under WORKDIR,
# so it needs a writable /app.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=20s --start-period=15s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health', timeout=15.0).raise_for_status()"

EXPOSE 8000

CMD ["uvicorn", "q_guardian.main:app", "--host", "0.0.0.0", "--port", "8000"]
