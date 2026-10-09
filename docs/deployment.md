# Deployment

## Docker

The image builds the client, installs the pinned runtime dependencies and gunicorn, prebuilds the dataset images and runs as an unprivileged user:

```sh
docker build -t joinery .
docker run --rm -p 8000:8000 \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 1g --cpus 2 \
  joinery
```

Every flag above is supported and recommended: the container never writes outside `/tmp` and needs no capabilities. The health check calls `/api/health`. Build with `--build-arg WITH_ENGINES=1` to include the DuckDB and server-engine drivers.

## Compose

`docker compose up --build` runs the same hardened container on `127.0.0.1:8000`. The `engines` profile adds PostgreSQL 18, MySQL 9.7 and SQL Server 2025, runs provisioning once they are healthy, and serves a second instance with every engine on port 8001. Set `JOINERY_ADMIN_PASSWORD` and `JOINERY_SANDBOX_PASSWORD` in your environment or a `.env` file instead of relying on the defaults.

## Sizing

Each run is a short-lived process of about 25 to 60 MB that lives for tens of milliseconds. With the default four sandbox slots and two gunicorn workers, one container runs at most eight queries at once; extra requests queue for up to 10 seconds. Raise `JOINERY_MAX_CONCURRENCY` and the container's CPU and memory together. The service is stateless, so it scales horizontally behind a load balancer without sticky sessions.

## Behind a reverse proxy

Terminate TLS at a proxy such as Caddy, nginx or a cloud load balancer, and set `JOINERY_TRUST_PROXY=true` so rate limiting sees client addresses. The built-in limiter is per process; for several processes or hosts, add a shared limit at the proxy, for example `limit_req` in nginx on `POST /api/`. Keep responses uncompressed for `/api/` if you are worried about compression side channels; there are no secrets in responses, so this is optional.

## Static hosting

The client is plain files in `web/dist` and can live on a CDN, but it needs the API on the same origin because the Content Security Policy only allows `connect-src 'self'`. Proxy `/api/` to Joinery, or serve both from Joinery as the image does.

## Upgrades

Dataset images rebuild automatically when the generator code or SQLite version changes, because the manifest stores a fingerprint of both. Lesson content is loaded at startup, so deploy a new image to publish content changes. Progress lives in learners' browsers and survives upgrades; exercise IDs are its keys, so do not rename them.

## GitHub Actions

Workflows run on every push and pull request (`CI`, `CodeQL`), and on a schedule or manually (`Engines`). Dependabot opens weekly update pull requests for pip, npm, GitHub Actions and the Docker base images.
