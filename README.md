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
* v2 POSTの永続`Idempotency-Key`により同一要求の安全な再送を保証
* healthでcontract/API profile/build/schema fingerprintを公開し、接続前に契約不一致を検出

Schemaの正本はwheelに同梱される`src/theme_compare/schemas`です。Custom GPT Actionの正本は `tools/generate_action_openapi.py` から生成するv2-only OpenAPIです。手書きのURL差替えやPowerShell内でのSchema再定義は行いません。

## Development

```bash
PIP_CONSTRAINT=constraints-dev.txt python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy src
pytest -q
```

## Production usage

1. `.env.example`から長いBearer secretと永続volumeを設定します。
2. Docker Linux containerとしてruntimeを起動します。
3. Windowsでは `deploy/setup-ngrok.ps1` を実行し、ngrok Freeの固定Development Domainを `127.0.0.1:8000` へ接続します。Cloudflare Named Tunnelは代替構成として利用できます。`trycloudflare.com` Quick Tunnelはproductionでは使用しません。
4. 固定URLからv2-only Action Schemaを生成します。

```powershell
.\deploy\setup-ngrok.ps1 -InstallStartupTask
python .\tools\generate_action_openapi.py `
  --server-url $env:THEME_COMPARE_PUBLIC_URL `
  --output .\openapi\custom-gpt-action.v2.openapi.json
```

`setup-ngrok.ps1` は既存ngrokのインストール・config/authenticationを確認し、既存endpointを再利用または `ngrok http 8000` を起動してpublic HTTPS URLを検出します。authtokenは読み出し・出力・リポジトリ保存しません。`-InstallStartupTask` を付けると現在のユーザーのWindowsログオン時にngrokを起動するタスクも作成します。

5. 生成ファイルをCustom GPT Actionsへimportし、Bearer API keyを設定します。
6. `docs/custom-gpt-production-instructions.md`をGPT Instructionsへ反映します。
7. `$env:THEME_COMPARE_API_KEY` を設定して `./deploy/verify-production.ps1` を実行し、`READY: Theme Candidate Stock Comparison v2` を確認します。

`GET /health`以外は認証されます。v2のsession create / phase submit / update startは`Idempotency-Key`を必須とし、同じkey+payloadの再送は最初の保存済み結果を返します。同じkeyを別payloadへ再利用すると拒否されます。

詳細なngrok bootstrap、自動起動、Cloudflare代替構成、backup、secret rotation、OpenAPI生成、smoke test、rollback手順は [`deploy/README.md`](deploy/README.md) を参照してください。

### Windows / Docker Desktop

Production runtimeはLinux containerを正式サポート範囲とし、Windowsではnative Python runtimeを直接起動せずDocker DesktopのLinux containers modeを使用します。

```powershell
Copy-Item .env.example .env
Docker build -t theme-compare:latest .
Docker run -d --name theme-compare --restart unless-stopped --env-file .env `
  -p 127.0.0.1:8000:8000 -v theme-compare-data:/data/sessions theme-compare:latest
Invoke-RestMethod http://127.0.0.1:8000/health
.\deploy\setup-ngrok.ps1 -InstallStartupTask
```

本runtimeは投資助言、具体的買値、分割購入、損切り、注文執行、自動売買を提供しません。
