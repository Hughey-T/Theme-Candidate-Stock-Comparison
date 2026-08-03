# Theme Candidate Stock Comparison Runtime

市場テーマ分析と個別株完全分析の間に置く、**Custom GPTが生成したPhase成果物を検証・保存するruntime**です。本リポジトリ自身は市場データ取得や分析文章の生成を行いません。Custom GPTがPhase-specific contractに従ってFACTS、COMPANY_CLAIMS、EXTERNAL_ESTIMATES、JUDGMENTSとpayloadを生成し、runtimeはSchema、identity、時系列、比較可能性、シナリオ計算、ranking、選抜、publication integrityを保証します。

## Operation and boundaries

Preferred contract **2.0.0** is Initial 12 / Update 4 with exact `次` / `更新` and one response per Phase. The four persisted results—evidence-only mechanical, AI-assumption scenario-derived, blind independent AI, and integrated selection—are different objects and never overwrite one another. The AI is frozen before machine or upstream ranks are disclosed. Runtime does not generate market analysis. Hard gates cannot be removed by AI, a relative winner is not necessarily investable, and `NO_SELECTION` is a formal result.

Candidate sets have separate identities for the ≤12 initial, ≤8 eligible, ≤5 deep, and ≤2/empty final sets. Multiple versioned horizons are first-class. Individual stock analysis receives a non-persuasive blind handoff first; reconciliation is released only after acknowledgement of independent analysis. This is not automated trading and has no broker, order, concrete entry-price, position-sizing, or stop-loss integration.

Contract 1.0 Initial 10 / Update 2 endpoints remain a legacy completion/read path. They are not silently migrated. See [the audit](docs/current-state-audit.md), [2.0 architecture](docs/final-architecture-v2.md), and [migration rules](docs/current-state-audit.md).

## Safety mechanisms

* legal-security identity全体からorder-independent candidate-set IDを再計算
* 共通THEME_BEAR/BASE/BULLからTSR、annualized return、downside/permanent-loss確率を再計算
* applicability、data state、comparability、dependency root、正規化scoreから5 rankingを再導出
* hard gateを加点で相殺せず、cash/investment benchmarkとリスク条件からoverall `SELECTION`/`NO_SELECTION`を分離
* 12 Phaseの内部までclosedなpackage-resource Schemaと必須phase semantic dispatcher
* Phase 2 canonical detail setに対するPhase 3～10の完全candidate coverageとpair/metric matrix検証
* generation evidence registryによる分類・ID・cutoff・全payload referenceの整合性検証
* complete generationから何度でも更新し、generation固有のcanonical candidate setとas-of/cutoffを履歴保持
* Phase 6/8/9・evidence・confidenceをhandoffへ実データ投影し、validated update context changesだけを重ねてhandoff chainをatomic supersede
* source cutoffをUTC instantで厳密単調増加させ、同一instantのoffset違いと逆行を拒否
* NaN/Infinity、duplicate JSON key、不正UTF-8を拒否するstrict runtime decode
* base64のclosed JSON partsをtemporary directoryで生成・復元検証してatomic rename
* remote integrity verification後だけlatestを更新

Schemaの正本はwheelに同梱される`src/theme_compare/schemas`です。Runtimeは`importlib.resources`で読み、source checkout、editable install、wheel installの経路差を作りません。Windowsを含めsymlinkを必要とせず、generatorとtestsもpackage resource pathを直接使用します。

Handoff v2はupdate operationとsnapshot data stateを分離し、confidence、catalyst、risk、invalidationをclosed typed objectで保存します。Candidate別assumption/evidenceは個別mapとして保存し、candidate changeの入力順に依存しない決定的なhandoffを生成します。

Initial evidenceはsourceの`candidate_id`によりglobalとcandidate-boundへpartitionし、global evidenceやglobal judgment assumptionsを全candidateへ複製しません。State loadはactive/supersededを含む全handoffのpartitionをgeneration evidence registryと再照合します。

## Development

Tool versions are pinned in `constraints-dev.txt`; dependency ranges in `pyproject.toml` prevent accidental major-version drift. Update pins only with a green Python 3.11–3.13 matrix.

```bash
PIP_CONSTRAINT=constraints-dev.txt python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy src
pytest -q
```

本runtimeは投資助言、具体的買値、分割購入、損切り、注文執行を提供しません。

## 実際の利用方法（private runtime）

1. `.env.example`から長いBearer secretと永続volumeを設定し、`docker build -t theme-compare .`でbuildします。
2. HTTPS reverse proxyの背後でcontainerを起動し、`openapi/custom-gpt-action.openapi.yaml`のserver URLを置換してCustom GPT Actionsへimportします。
3. Action認証をBearer API keyに設定し、`docs/custom-gpt-production-instructions.md`をGPT Instructionsへ追加します。
4. 上流handoffから`POST /v1/sessions`を1回実行します。以後「次」はnext-contract取得→Custom GPTによる単一Phase調査→artifact submissionだけを行い、Initial完了後の「更新」は新generationを開始します。

serviceは`GET /health`以外を認証し、stateを`THEME_COMPARE_STORAGE_ROOT`へsession単位でatomic保存します。endpoint、backup、secret rotation、Preview試験、更新手順の詳細は[`deploy/README.md`](deploy/README.md)を参照してください。

### Windows / Docker Desktop

Production runtimeはLinux containerを正式サポート範囲とし、Windowsでは`fcntl`へ依存するPython processを直接起動せずDocker Desktopを使用します。PowerShell例:

```powershell
Copy-Item .env.example .env
# .envのTHEME_COMPARE_API_KEYを十分長いrandom secretへ変更
Docker build -t theme-compare:latest .
Docker run -d --name theme-compare --env-file .env -p 127.0.0.1:8000:8000 -v theme-compare-data:/data/sessions theme-compare:latest
Invoke-RestMethod http://127.0.0.1:8000/health
```
