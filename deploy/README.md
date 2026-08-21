# Deployment runbook

## Supported production topology

Default production ingress is:

`Custom GPT Action -> fixed ngrok Development Domain -> ngrok agent -> 127.0.0.1:8000 -> Docker container -> named volume`

Cloudflare Named Tunnel remains a supported alternative when an independent domain/DNS setup is preferred. Do **not** use Quick Tunnel / `trycloudflare.com` for production. The Action server hostname must remain stable across container, tunnel-agent, and machine restarts.

ngrok Free accounts include an account-assigned Development Domain whose URL remains fixed across agent restarts. This is sufficient for the personal Custom GPT integration as long as account limits are acceptable.

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
- discovers the public HTTPS URL from the local ngrok API
- saves `THEME_COMPARE_PUBLIC_URL` as a user environment variable
- verifies `/health` through the public endpoint

It does not read, print, copy, or commit an ngrok authtoken. If the machine has never been authenticated, ngrok itself must first be configured with `ngrok config add-authtoken <YOUR_AUTHTOKEN>`.

To install a current-user logon task that starts ngrok after Windows sign-in:

```powershell
.\deploy\setup-ngrok.ps1 -InstallStartupTask
```

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
  --server-url https://your-assigned-domain.ngrok-free.app \
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

If the startup task cannot be installed because of local Windows policy, the only remaining manual operation is starting `ngrok http 8000` after sign-in. The account-assigned Development Domain remains the same.

## Contract 2.0 rollout and rollback

New GPT integrations use only the v2 Action contract. Keep runtime `/v1` endpoints available while active 1.0 sessions finish; do not expose them in the new GPT Action schema. Do not point an existing v1 session at v2 or infer/migrate missing v2 state. Completed v1 publications remain immutable/read-only.

Rollback deploys the prior image with the same persistent volume. Preserve `*.json`, `*.v2.json`, and `.idempotency/`; do not convert or delete v2 state during rollback.
