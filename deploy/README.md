# Deployment runbook

## Supported production topology

Default production ingress is:

`Custom GPT Action -> fixed ngrok Development Domain -> ngrok agent -> 127.0.0.1:8000 -> Docker container -> named volume`

Cloudflare Named Tunnel remains a supported alternative when an independent domain/DNS setup is preferred. Do **not** use Quick Tunnel / `trycloudflare.com` for production. The Action server hostname must remain stable across container, tunnel-agent, and machine restarts.

ngrok Free accounts include an account-assigned Development Domain whose URL remains fixed across agent restarts. Current ngrok-branded development domains may use `ngrok-free.app` or `ngrok-free.dev`. This is sufficient for the personal Custom GPT integration as long as account limits are acceptable.

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
- requires the new `/health` response to report `service=ok`, `storage=ok`, `ready=true`, contract `2.0.0`, profile `custom-gpt-v2`, and a schema fingerprint
- automatically attempts to restore the old container if replacement startup or health validation fails
- never performs `docker volume rm`, volume prune, or system prune

On success it prints:

`RUNTIME READY: Theme Candidate Stock Comparison v2`

The stopped rollback container/image are intentionally retained after a successful update. Remove old rollback artifacts only as a separate deliberate maintenance operation after confirming the new runtime and persisted state; never remove the persistent data volume.

## Default ingress: ngrok Free Development Domain

On Windows, after the runtime is healthy on `http://127.0.0.1:8000`, run:

```powershell
.\deploy\setup-ngrok.ps1
```

The bootstrap script:

- discovers the existing `ngrok` executable on PATH
- validates the existing ngrok config/authentication
- refuses to proceed unless the local runtime is ready
- reuses an already-running ngrok HTTPS endpoint or starts `ngrok http 8000`
- accepts current ngrok development-domain suffixes including `ngrok-free.app` and `ngrok-free.dev`
- discovers the public HTTPS URL from the local ngrok API
- saves `THEME_COMPARE_PUBLIC_URL` as a user environment variable
- verifies the full v2 production `/health` fingerprint through the public endpoint

It does not read, print, copy, or commit an ngrok authtoken. If the machine has never been authenticated, ngrok itself must first be configured with `ngrok config add-authtoken <YOUR_AUTHTOKEN>`.

To configure automatic ngrok startup after Windows sign-in:

```powershell
.\deploy\setup-ngrok.ps1 -InstallStartupTask
```

The script first attempts a current-user Task Scheduler registration. If local Windows policy rejects that registration, it falls back to a hidden launcher shortcut in the current user's Startup folder, which does not require administrator elevation. Failure to use Task Scheduler therefore does not block public health verification.

The Docker runtime already uses `--restart unless-stopped`; Docker Desktop itself must be configured to start with Windows for full automatic recovery after a reboot.

The ngrok endpoint is an ingress only. Runtime authentication still requires the Theme Comparison Bearer API key, so exposing the endpoint does not bypass API authentication.

## Alternative ingress: Cloudflare Named Tunnel

A remotely managed / named Cloudflare Tunnel may instead map a DNS hostname you control, for example `theme-compare.your-domain.tld`, to `http://127.0.0.1:8000`. Keep tunnel token/credentials outside the repository and configure cloudflared to restart automatically. Do not bake tunnel credentials into the image.

The runtime does not depend on ngrok- or Cloudflare-specific request headers; any stable HTTPS reverse proxy may be used.

## Generate the only supported Custom GPT Action schema

There is one generator for the v2-only Action contract. With ngrok, `THEME_COMPARE_PUBLIC_URL` is populated by `setup-ngrok.ps1`:

```powershell
python .\tools\generate_action_openapi.py `
  --server-url $env:THEME_COMPARE_PUBLIC_URL `
  --output .\openapi\custom-gpt-action.v2.openapi.json
```

Equivalent shell usage:

```bash
python tools/generate_action_openapi.py \
  --server-url https://your-assigned-domain.ngrok-free.dev \
  --output openapi/custom-gpt-action.v2.openapi.json
```

The generator rejects HTTP, `trycloudflare.com`, common example domains, `.invalid`, and origins containing a path/query/fragment. It emits only `/v2/*` plus `/health`; legacy `/v1/*` operations are intentionally excluded from the GPT Action contract.

Import `openapi/custom-gpt-action.v2.openapi.json` in GPT editor -> Configure -> Actions, then configure API Key authentication as Bearer using `THEME_COMPARE_API_KEY`. Do not manually edit or paste-rewrite the generated JSON.

## One-command production verification (Windows)

After `setup-ngrok.ps1`, set only the runtime API key in the current shell and run:

```powershell
$env:THEME_COMPARE_API_KEY = '<secret>'
.\deploy\verify-production.ps1
```

For another stable HTTPS provider, set `THEME_COMPARE_PUBLIC_URL` explicitly before running the verifier.

The verifier checks:

- public health/readiness
- contract version and API profile
- schema fingerprint presence
- unauthenticated `401`
- deterministic v2-only Action generation
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

The v2 Action requires `Idempotency-Key` for session creation, phase submission, and update start. Repeating the same logical request with the same key and payload returns the persisted first result. Reusing a key with different payload is rejected. Records live under the same persistent storage root and survive runtime restarts.

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
.\deploy\setup-ngrok.ps1 -InstallStartupTask
```

For subsequent code updates, run `deploy/update-production.ps1` instead of manually stopping/removing/recreating the production container.

If Task Scheduler registration is blocked by local Windows policy, `setup-ngrok.ps1 -InstallStartupTask` automatically falls back to the current user's Startup folder. The account-assigned Development Domain remains the same.

## Contract 2.0 rollout and rollback

New GPT integrations use only the v2 Action contract. Keep runtime `/v1` endpoints available while active 1.0 sessions finish; do not expose them in the new GPT Action schema. Do not point an existing v1 session at v2 or infer/migrate missing v2 state. Completed v1 publications remain immutable/read-only.

`update-production.ps1` retains the previous container and image under timestamped rollback names and uses the same persistent mounts. If automated health validation fails, it attempts to restore the previous container immediately. Preserve `*.json`, `*.v2.json`, `.idempotency/`, and the persistent volume; do not convert or delete state during rollback.