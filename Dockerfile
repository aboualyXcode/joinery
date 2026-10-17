# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- web client
FROM node:26-alpine AS web
WORKDIR /src
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY tsconfig.json ./
COPY scripts ./scripts
COPY web ./web
RUN npm run typecheck && npm run build

# ---------------------------------------------------------------- runtime
FROM python:3.13-slim AS runtime
ARG WITH_ENGINES=0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JOINERY_DATA_DIR=/app/var/datasets
WORKDIR /app
COPY requirements.txt requirements-prod.txt requirements-engines.txt ./
RUN pip install -r requirements-prod.txt \
 && if [ "$WITH_ENGINES" = "1" ]; then pip install -r requirements-engines.txt; fi
COPY joinery ./joinery
COPY content ./content
COPY --from=web /src/web/dist ./web/dist
# Build the dataset images now, so the container can run with a read-only root filesystem.
RUN python -m joinery build-datasets \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin joinery
USER joinery
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status != 200)"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "60", \
     "--worker-tmp-dir", "/dev/shm", "--access-logfile", "-", "joinery.app:create_app()"]
