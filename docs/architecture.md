# Architecture and responsibility

正本は選択肢A（validator/persistence runtime）である。Custom GPTが各Phaseのevidence分類、judgments、phase payloadを生成する。runtimeは `read bytes → JSON decode → JSON Schema → semantic validation → transition → atomic write` を行う。市場data adapter、LLM呼出、分析文章生成、source内容の真偽判定は対象外である。

Initial generationは10 artifacts、update generationは2 artifactsを持ち、generation_historyを上書きしない。Phase 7の共通scenario値からreturnを、atomic metricsから5 rankingsを、benchmarks/hard gates/risk limitsからoverall decisionと最大2候補を再導出する。publicationはbase64 closed part、exact inventory、hash、atomic generation rename、明示的persistence lifecycleを使用する。
