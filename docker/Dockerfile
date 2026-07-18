FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY src/ src/
COPY pyproject.toml .

# Non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health').raise_for_status()"

EXPOSE 8000

CMD ["uvicorn", "src.q_guardian.main:app", "--host", "0.0.0.0", "--port", "8000"]
