# Queer the Stacks — self-hosted reading dashboard.
# Single-user, private; runs behind auth next to Calibre-Web on the seedbox.
FROM python:3.14-slim

# Don't run as root.
RUN useradd --create-home --uid 10001 stacks
WORKDIR /app

# Install dependencies first for layer caching.
COPY pyproject.toml README.md LICENSE ./
COPY ingest ./ingest
COPY recommender ./recommender
COPY app ./app
RUN pip install --no-cache-dir -e ".[app]"

# Derived app state lives here; mount a volume to persist it.
ENV STACKS_DATA_DIR=/data
RUN mkdir -p /data && chown -R stacks:stacks /data /app
USER stacks

EXPOSE 8765

# Health: GET /healthz. Auth is REQUIRED — set STACKS_AUTH_TOKEN at run time
# (the app fails closed if it is unset and demo mode is off).
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz').status==200 else 1)"

CMD ["python", "-m", "uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8765"]
