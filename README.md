# Theme Candidate Stock Comparison

市場テーマ分析と個別株完全分析の間に置く、再現可能な比較・選抜ゲートです。候補（最大12）を Phase 1 で8、詳細比較で5、handoffで2以下へ絞ります。会話履歴でなく永続JSON stateを毎回再読込し、generation、candidate set、cutoffを固定します。

## Operation

ユーザー操作は `次`（現在の1 Phaseだけを実行）と、初回完了後の `更新`（新generationで更新を開始）だけです。初回は10 Phase、更新は2 Phaseです。壊れたlatest、hash/schema/semantic不整合、mixed generationでは停止し、旧版へフォールバックしません。

## Components

* `state.py`: 再開可能な厳格状態機械。
* `validation.py`: 候補同一性、時系列、比較可能性、依存指標、シナリオ、選抜の再計算。
* `engine.py`: 共通シナリオ、期待値、hard gate優先の分類、NO_SELECTION、diff、handoff。
* `publication.py`: immutable generation、48KB part、raw/canonical SHA-256、復元検証。
* `schemas/`: generatorから作られる10個のclosed Draft 2020-12 Schema。

## Development

```bash
python -m pip install -e '.[dev]'
ruff check . && ruff format --check .
mypy src
pytest -q
```

投資助言・売買価格・損切りを提供するものではありません。一次資料のas-of/cutoffを記録し、判断には反対証拠を必須とします。
