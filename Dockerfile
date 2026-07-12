# Queer the Stacks — self-hosted reading dashboard.
# Single-user, private; runs behind auth next to Calibre-Web on the seedbox.

# --- Stage 1: export the locked, hash-pinned runtime requirement set --------
# Ties the deployed image's dependency versions to the same `uv.lock` that CI
# enforces (CQ-28, SEC-13's "lockfile scanned" leg) instead of re-resolving
# against upstream indexes at build time. Built on the same pinned Debian-slim
# base as the runtime stage (the standalone `ghcr.io/astral-sh/uv` image has no
# shell, so `RUN uv export` needs a normal base — just grab the `uv` binary
# from it via `COPY --from`).
FROM python:3.14-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1 AS export
COPY --from=ghcr.io/astral-sh/uv:0.11.26@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --extra app --no-dev --no-emit-project -o requirements.lock.txt

# --- Stage 2: runtime image --------------------------------------------------
# Pinned by digest (Scorecard Pinned-Dependencies; bump both the tag and the
# digest together when upgrading — `docker pull python:3.14-slim && docker
# inspect --format='{{index .RepoDigests 0}}' python:3.14-slim`).
FROM python:3.14-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1

# Don't run as root.
RUN useradd --create-home --uid 10001 stacks
WORKDIR /app

# Install the locked, hash-verified runtime dependency set first (layer
# caching); every artifact's hash is checked against uv.lock before install.
COPY --from=export /app/requirements.lock.txt ./requirements.lock.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.lock.txt

# Install this package itself, without re-resolving deps (already satisfied
# and hash-verified above).
COPY pyproject.toml README.md LICENSE ./
COPY ingest ./ingest
COPY recommender ./recommender
COPY app ./app
RUN pip install --no-cache-dir --no-deps .

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
