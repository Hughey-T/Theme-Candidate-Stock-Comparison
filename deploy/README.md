# Deployment runbook

## Local and production startup

```bash
cp .env.example .env                 # edit secret; never commit .env
python -m pip install -e .
THEME_COMPARE_STORAGE_ROOT="$PWD/data" THEME_COMPARE_API_KEY='secret' theme-compare serve

docker build -t theme-compare:latest .
docker run -d --name theme-compare --restart unless-stopped --env-file .env \
  -p 127.0.0.1:8000:8000 -v theme-compare-data:/data/sessions theme-compare:latest
```

Production requires an HTTPS reverse proxy in front of the loopback-bound container. Restrict ingress and do not log Authorization headers or request bodies. The named volume is mandatory for restart continuity.

## Custom GPT Action and Preview

1. Replace `https://YOUR_PRIVATE_RUNTIME_HOST` in `openapi/custom-gpt-action.openapi.yaml` with the HTTPS origin.
2. GPT editor → Configure → Actions → Import from file, and select the OpenAPI 3.1 file.
3. Authentication → API Key → Bearer and enter `THEME_COMPARE_API_KEY`.
4. In Preview call health, create a test session from an upstream handoff, then enter「次」and confirm exactly one contract/submission pair.

## Operations

Backup while writes are quiesced: `docker run --rm -v theme-compare-data:/data -v "$PWD":/backup alpine tar czf /backup/theme-compare.tgz -C /data .`. Restore into an empty volume with `tar xzf`; retain exact JSON bytes and permissions. A corrupted latest state intentionally stops and must not be replaced automatically by an older copy.

Rotate secrets by generating a new random value, updating both service environment and GPT Action authentication, then restarting promptly. Inspect metadata-only service logs with `docker logs --since 1h theme-compare`; never enable body/header logging.

To update, build a versioned image, run tests and its health check, stop the old container, start the new image with the same persistent volume, and verify an existing session. Keep an external backup before migration.
