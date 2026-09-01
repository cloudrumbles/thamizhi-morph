FROM python:3.13-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends foma-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY FST-Models ./FST-Models
RUN python -m pip install --no-cache-dir '.[api]'

ENV THAMIZHI_MODELS=/app/FST-Models \
    PYTHONUNBUFFERED=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["thamizhi-morph", "serve", "--host", "0.0.0.0", "--port", "8000"]
