# Deployment runbook

## Supported production topology

Default production ingress uses the shared **Local AI Gateway** managed by the AI Development Orchestrator repository:

```text
Custom GPT Action
  -> fixed ngrok Development Domain
  -> ngrok agent
  -> 127.0.0.1:8080
  -> Caddy Local AI Gateway
  -> /theme-compare/*
  -> theme-compare:8000
  -> persistent theme-compare-data volume
```

The same public domain root `/` continues to route to AI Development Orchestrator. Theme Comparison therefore consumes a stable public base path such as:

`https://<assigned-domain>.ngrok-free.dev/theme-compare`

Theme Comparison does **not** own a second ngrok process or Development Domain. This avoids Free-plan domain collisions and gives future local systems another unique top-level path on the same gateway.

Cloudflare Named Tunnel remains a supported alternative when an independent domain/DNS setup is preferred. Do **not** use Quick Tunnel / `trycloudflare.com` for production.

## Runtime startup

```bash
cp .env.example .env                 # edit secret; never commit .env
docker build -t theme-compare:latest .
docker run -d --name theme-compare --restart unless-stopped --env-file .env \
  -e THEME_COMPARE_BUILD_ID="$(git rev-parse --short HEAD)" \
  -p 127.0.0.1:8000:8000 \
  -v theme-compare-data:/data/sessions \
  theme-compare:latest
```

The named volume is mandatory for session and idempotency continuity. Restrict ingress and never log Authorization headers or request bodies.

## Safe runtime update on Windows

After the first production container exists, update it with:

```powershell
.\deploy\update-production.ps1
```

The updater is intentionally conservative. It:

- requires a clean git working tree
- requires the existing `theme-compare` container to be running
- requires the runtime to be bound exactly to `127.0.0.1:8000`
- records and reuses the current persistent volume/bind mounts, effective environment, and restart policy without printing environment values
- builds a timestamped candidate image before stopping the old container
- tags the old image and renames the old container with timestamped rollback names instead of deleting them
- starts the replacement with the same mounts and environment
- preserves membership in the shared `local-ai-gateway` Docker network when it is already present, restoring alias `theme-compare` on the replacement
- requires the new `/health` response to report `service=ok`, `storage=ok`, `ready=true`, contract `2.0.0`, profile `custom-gpt-v2`, and a schema fingerprint
- automatically attempts to restore the old container if replacement startup or health validation fails
- never performs `docker volume rm`, volume prune, or system prune

On success it prints:

`RUNTIME READY: Theme Candidate Stock Comparison v2`

## Orchestrator-owned dispatch, target-owned deployment

`.github/workflows/deploy-production.yml` is the repository-owned Stage 5 wrapper
for the same updater. It runs automatically for `main` pushes on the dedicated
`theme-production` Windows runner and also permits manual dispatch with an optional
exact 40-character `commit_sha`. It refuses to deploy unless that SHA
is both checked out and still the current `main` commit. GitHub serializes
production updates without cancelling an update already in progress.

Automatic production deployment tracks the exact commit SHA at the tip of `main`.

Configure the Orchestrator with:

```env
GITHUB_WORKFLOW_ALLOWLIST=Hughey-T/Theme-Candidate-Stock-Comparison:deploy-production.yml
GITHUB_WORKFLOW_INPUT_SCHEMAS={"Hughey-T/Theme-Candidate-Stock-Comparison:deploy-production.yml":{"commit_sha":{"required":true,"pattern":"^[0-9a-f]{40}$","maxLength":40}}}
DEPLOYMENT_TARGETS={"Hughey-T/Theme-Candidate-Stock-Comparison":{"workflow":"deploy-production.yml","environment":"production","mode":"auto","event":"push"}}
```

The runner holds no deployment secret: `update-production.ps1` reconstructs the
existing container's effective environment in a temporary file and preserves its
mounts, restart policy, loopback binding, and shared Gateway network. The workflow
conclusion is Stage 5 deployment-process evidence. Independent public HTTP/API/
browser acceptance remains the Stage 6 human-review gate.

The stopped rollback container/image are intentionally retained after a successful update. Remove old rollback artifacts only as a separate deliberate maintenance operation after confirming the new runtime and persisted state; never remove the persistent data volume.

## Shared Local AI Gateway

The Gateway is bootstrapped from the AI Development Orchestrator repository after both application containers are healthy:

```powershell
.\deploy\setup-gateway.ps1
```

That bootstrap creates/reuses the external Docker network `local-ai-gateway`, connects this container with alias `theme-compare`, starts pinned Caddy on `127.0.0.1:8080`, and verifies:

```text
http://127.0.0.1:8080/health                -> Orchestrator
http://127.0.0.1:8080/theme-compare/health  -> Theme Comparison v2
```

Only after those local checks pass should the single central ngrok Development Domain be pointed at port `8080`.

The gateway strips `/theme-compare` before forwarding, so this runtime itself remains unaware of the public prefix and continues serving `/health` and `/v2/*` internally.

## Theme public-ingress setup

After the central ngrok tunnel points to the Gateway on `127.0.0.1:8080`, run:

```powershell
.\deploy\setup-ngrok.ps1
```

Despite the historical filename, this script no longer starts a Theme-specific ngrok tunnel. It:

- verifies the local Theme runtime on `127.0.0.1:8000`
- verifies the local Gateway route at `/theme-compare/health`
- discovers the existing ngrok HTTPS endpoint from the local ngrok API
- accepts it only when its upstream is the central Gateway port `8080`
- constructs `https://<fixed-domain>/theme-compare`
- saves that value as `THEME_COMPARE_PUBLIC_URL`
- removes obsolete Theme-specific ngrok Startup shortcut/launcher entries if present
- verifies the full v2 health fingerprint through the public Gateway route

`-InstallStartupTask` is retained only for backwards compatibility. It does not create another Theme-specific startup entry because central ngrok lifecycle belongs to the Gateway.

The script does not read, print, copy, or commit an ngrok authtoken.

## Generate the supported Custom GPT Action schema

Use the canonical generator with the prefixed public base:

```powershell
python .\tools\generate_action_openapi.py `
  --server-url $env:THEME_COMPARE_PUBLIC_URL `
  --output .\openapi\custom-gpt-action.v2.openapi.json
```

Example:

```bash
python tools/generate_action_openapi.py \
  --server-url https://your-assigned-domain.ngrok-free.dev/theme-compare \
  --output openapi/custom-gpt-action.v2.openapi.json
```

The generator accepts a stable lowercase slug path prefix such as `/theme-compare`, places it in OpenAPI `servers.url`, and leaves the canonical operation paths as `/health` and `/v2/*`. It rejects HTTP, `trycloudflare.com`, placeholder domains, query/fragment values, and unsafe path forms.

Import `openapi/custom-gpt-action.v2.openapi.json` in GPT editor -> Configure -> Actions, then configure API Key authentication as Bearer using `THEME_COMPARE_API_KEY`. Do not manually edit or paste-rewrite the generated JSON.

## One-command production verification (Windows)

After the shared public ingress is configured, set only the runtime API key in the current shell and run:

```powershell
$env:THEME_COMPARE_API_KEY = '<secret>'
.\deploy\verify-production.ps1
```

The verifier checks:

- public health/readiness through `/theme-compare`
- contract version and API profile
- schema fingerprint presence
- unauthenticated `401`
- deterministic v2-only Action generation with the prefixed server base
- authenticated v2 test-session creation
- idempotent replay returning the same session
- next-contract readback at Initial Phase 1

Success ends with `READY: Theme Candidate Stock Comparison v2`.

## Health contract

`GET /health` remains unauthenticated and reports at least:

- `service`
- `storage`
- `ready`
- `contract_version`
- `api_profile`
- `build_id`
- `schema_sha256`

A GPT/runtime deployment mismatch should therefore be detectable before creating a session.

## Idempotent POSTs

The v2 Custom GPT Action requires the `idempotency_key` query parameter for session creation, phase submission, and update start. The runtime also accepts the legacy `Idempotency-Key` header for backwards compatibility; either form is sufficient, and if both are supplied they must agree. Repeating the same logical request with the same key and payload returns the persisted first result. Reusing a key with different payload is rejected. Records live under the same persistent storage root and survive runtime restarts.

## Adding future local systems

Do not modify this repository for unrelated services. Add future routes in the Gateway repository's `gateway/services.json`, connect the future container to `local-ai-gateway` with a unique alias, regenerate the Caddy config, and verify the new prefix locally before exposing it publicly.

The shared conventions are:

- `/` is reserved for AI Development Orchestrator
- `/__gateway/*` is reserved for Gateway health/administration
- `/theme-compare/*` belongs to this runtime
- every future service receives another unique lowercase top-level slug
- reverse-proxy routing never replaces each backend's own authentication

## Alternative ingress: Cloudflare Named Tunnel

A named Cloudflare Tunnel may instead map a stable hostname you control directly to this runtime or to the shared Gateway. Keep tunnel token/credentials outside the repository and configure cloudflared to restart automatically. Do not bake tunnel credentials into the image.

## Operations

Backup while writes are quiesced:

```bash
docker run --rm -v theme-compare-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/theme-compare.tgz -C /data .
```

The backup includes v1 state, v2 state, and `.idempotency` records. Restore into an empty volume and verify health plus an existing session before accepting traffic. A corrupted latest state intentionally stops and must not be silently replaced by an older copy.

Rotate secrets by updating both the service environment and GPT Action authentication, then restart promptly. Inspect metadata-only logs with `docker logs --since 1h theme-compare`; never enable request-body or Authorization-header logging.

## Windows / Docker Desktop

Windows production uses Docker Desktop in Linux containers mode. Native Windows Python runtime locking is not supported.

```powershell
Copy-Item .env.example .env
Docker build -t theme-compare:latest .
Docker run -d --name theme-compare --restart unless-stopped --env-file .env `
  -e THEME_COMPARE_BUILD_ID=$(git rev-parse --short HEAD) `
  -p 127.0.0.1:8000:8000 -v theme-compare-data:/data/sessions theme-compare:latest
Invoke-RestMethod http://127.0.0.1:8000/health
```

Then use the shared Gateway bootstrap. For subsequent code updates, run `deploy/update-production.ps1` instead of manually stopping/removing/recreating the production container.

## Contract 2.0 rollout and rollback

New GPT integrations use only the v2 Action contract. Keep runtime `/v1` endpoints available while active 1.0 sessions finish; do not expose them in the new GPT Action schema. Do not point an existing v1 session at v2 or infer/migrate missing v2 state. Completed v1 publications remain immutable/read-only.

`update-production.ps1` retains the previous container and image under timestamped rollback names and uses the same persistent mounts. If automated health validation fails, it attempts to restore the previous container immediately. Preserve `*.json`, `*.v2.json`, `.idempotency/`, and the persistent volume; do not convert or delete state during rollback.
