# Theme Candidate Stock Comparison Runtime

市場テーマ分析と個別株完全分析の間に置く、**Custom GPTが生成したPhase成果物を検証・保存するruntime**です。本リポジトリ自身は市場データ取得や分析文章の生成を行いません。Custom GPTがPhase-specific contractに従ってFACTS、COMPANY_CLAIMS、EXTERNAL_ESTIMATES、AI_ASSUMPTIONS、JUDGMENTS、UNRESOLVEDとpayloadを生成し、runtimeはSchema、identity、時系列、比較可能性、ranking、選抜、publication integrityを保証します。

## Operation and boundaries

Preferred contract **2.0.0** is Initial 12 / Update 4 with exact `次` / `更新` and one response per Phase. The four persisted results—evidence-only mechanical, AI-assumption scenario-derived, blind independent AI, and integrated selection—are different objects and never overwrite one another. The AI is frozen before machine or upstream ranks are disclosed. Runtime does not generate market analysis. Hard gates cannot be removed by AI, a relative winner is not necessarily investable, and `NO_SELECTION` is a formal result.

Candidate sets have separate identities for the ≤12 initial, ≤8 eligible, ≤5 deep, and ≤2/empty final sets. Multiple versioned horizons are first-class. Individual stock analysis receives a non-persuasive blind handoff first; reconciliation is released only after acknowledgement of independent analysis. This is not automated trading and has no broker, order, concrete entry-price, position-sizing, or stop-loss integration.

Contract 1.0 endpoints remain a legacy completion/read path inside the runtime only. New Custom GPT integrations expose **v2 only** and never silently migrate v1 state.

## Safety mechanisms

* legal-security identity全体からorder-independent candidate-set IDを再計算
* evidence-only / scenario-derived / independent AI / integrated selectionを別objectとして保持
* hard gateを加点で相殺せず、条件未達では正式に`NO_SELECTION`
* generation evidence registryによる分類・ID・cutoff・payload reference整合性検証
* source cutoffをUTC instantで厳密単調増加させ、逆行やfuture evidenceを拒否
* NaN/Infinity、duplicate JSON key、不正UTF-8を拒否するstrict runtime decode
* atomic persistenceとreadback verification
* Custom GPTではv2 POSTの必須query parameter `idempotency_key` により同一要求の安全な再送を保証。runtimeは既存クライアント互換のため`Idempotency-Key` headerも受理
* healthでcontract/API profile/build/schema fingerprintを公開し、接続前に契約不一致を検出

Schemaの正本はwheelに同梱される`src/theme_compare/schemas`です。Custom GPT Actionの正本は `tools/generate_action_openapi.py` から生成するv2-only OpenAPIです。

## Development

```bash
PIP_CONSTRAINT=constraints-dev.txt python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy src
pytest -q
```

## Production topology

複数のローカルシステムで1つの固定ngrok Development Domainを共有するため、production ingressは共有 **Local AI Gateway** を使用します。

```text
Custom GPT Action
  ↓
https://<fixed-ngrok-domain>/theme-compare
  ↓
ngrok
  ↓
Local AI Gateway (Caddy, 127.0.0.1:8080)
  ↓  /theme-compare prefixを除去
Theme Comparison container :8000
  ↓
persistent theme-compare-data volume
```

Gateway本体・ngrok起動・route registryは `AI-Development-Orchestrator` repository側で管理します。Theme Comparisonはngrokプロセスを独自に起動しません。Gatewayのdomain root `/` は既存AI Development Orchestrator用に維持されます。

## Production usage

1. `.env.example`から長いBearer secretと永続volumeを設定します。
2. Docker Linux containerとしてruntimeを起動します。
3. AI Development Orchestrator repositoryの `deploy/setup-gateway.ps1` で共有Gatewayへ `theme-compare` containerを接続します。
4. ngrokが共有Gatewayのport `8080` を公開した後、このrepositoryで次を実行します。

```powershell
.\deploy\setup-ngrok.ps1
```

このスクリプトはTheme専用ngrokを開始しません。ローカルGatewayの `/theme-compare/health`、中央ngrok tunnelのupstreamがport 8080であること、公開 `/theme-compare/health` のv2 fingerprintを確認し、次の形式で `THEME_COMPARE_PUBLIC_URL` を設定します。

```text
https://<fixed-ngrok-domain>/theme-compare
```

過去に作成されたTheme専用ngrok Startup shortcut/launcherがあれば削除します。旧 `-InstallStartupTask` switchは互換性のため受理しますが、新しいTheme専用自動起動は作りません。

5. 固定Gateway URLからv2-only Action Schemaを生成します。

```powershell
python .\tools\generate_action_openapi.py `
  --server-url $env:THEME_COMPARE_PUBLIC_URL `
  --output .\openapi\custom-gpt-action.v2.openapi.json
```

Generatorは `https://host/theme-compare` のような安全なpath prefixをOpenAPI `servers.url` として扱い、API path自体は既存の `/v2/*` と `/health` のまま維持します。

6. 生成ファイルをCustom GPT Actionsへimportし、Bearer API keyを設定します。
7. `docs/custom-gpt-production-instructions.md`をGPT Instructionsへ反映します。
8. `$env:THEME_COMPARE_API_KEY` を設定して `./deploy/verify-production.ps1` を実行し、`READY: Theme Candidate Stock Comparison v2` を確認します。

## Safe Windows runtime update

既存production containerの更新は個別Docker操作ではなく次を使います。

```powershell
.\deploy\update-production.ps1
```

このスクリプトはclean working tree、既存container、`127.0.0.1:8000` binding、persistent mountsを確認してからcandidate imageをbuildします。build成功後にのみ旧containerを停止し、旧containerと旧imageをtimestamp付きrollback対象として保持したまま、同じmount・effective environment・restart policyで新containerを起動します。新runtimeがv2 health contractを満たさない場合は旧containerへのrollbackを試みます。volume削除やpruneは行いません。

一度 `local-ai-gateway` networkへ接続されたproduction containerは、以後のruntime更新でも `theme-compare` alias付きnetwork membershipを自動で復元します。

`GET /health`以外は認証されます。Custom GPT Actionのv2 session create / phase submit / update startでは必須query parameter `idempotency_key` を使用し、runtimeは後方互換としてqueryまたは`Idempotency-Key` headerのいずれかを受理します。同じkey+payloadの再送は最初の保存済み結果を返します。同じkeyを別payloadへ再利用すると拒否されます。

詳細なruntime更新、共有Gateway ingress、backup、secret rotation、OpenAPI生成、smoke test、rollback手順は [`deploy/README.md`](deploy/README.md) を参照してください。

### Windows / Docker Desktop

Production runtimeはLinux containerを正式サポート範囲とし、Windowsではnative Python runtimeを直接起動せずDocker DesktopのLinux containers modeを使用します。

初回起動例:

```powershell
Copy-Item .env.example .env
Docker build -t theme-compare:latest .
Docker run -d --name theme-compare --restart unless-stopped --env-file .env `
  -p 127.0.0.1:8000:8000 -v theme-compare-data:/data/sessions theme-compare:latest
Invoke-RestMethod http://127.0.0.1:8000/health
```

その後、共有Gateway bootstrapを実行します。以後のコード更新は `deploy/update-production.ps1` を使用してください。

本runtimeは投資助言、具体的買値、分割購入、損切り、注文執行、自動売買を提供しません。
