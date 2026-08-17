ARG BASE_IMAGE=python:3.12.10-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src/ /app/src/
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 bot
USER bot

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; port=os.getenv('HEALTH_PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=2)"

ENTRYPOINT ["demo-account-bot"]
