# Architecture and responsibility

本repositoryはCustom GPTが生成したPhase成果物のvalidator/persistence runtimeであり、市場data取得や分析文章生成器ではない。Runtime boundaryは `read bytes → JSON decode → packaged JSON Schema → state/phase/cross-phase semantic validation → transition → resulting-state validation → atomic write` である。

Schemaはwheel package dataとして`theme_compare.schemas`に同梱し、`importlib.resources.files()`でsource/editable/wheelを同一経路から読む。Initial 10 artifactsとUpdate 2 artifacts、generation別as-of/cutoff、handoff履歴を上書きしない。Publicationはtemporary directory、exact inventory、on-disk manifest、base64 parts、atomic renameを使用する。
