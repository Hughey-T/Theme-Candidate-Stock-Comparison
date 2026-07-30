# Test matrix

Schema/type、候補追加削除順序/identity、comparability/data-state、scenario probability/price/share/dividend/permanent loss、ranking/hard gate/NO_SELECTION、generation/time、publication mutations、state replay/skip/resume/updateをpytestで実行する。代表mutationはcandidate set、probability、hash、part metadata、generation、phaseを実データ改変して失敗を確認する。CIは3.11/3.12/3.13 unit matrixに加えlint/type/schema/mutation/integration/fresh-clone E2E jobを持つ。
