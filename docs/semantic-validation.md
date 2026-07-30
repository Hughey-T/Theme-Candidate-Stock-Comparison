# Semantic validation

`validate_candidates` はID/legal security/alias/corporate-action重複と再計算set IDを検査する。`validate_envelope` はgeneration/set/cutoff統一、timezone、将来情報を検査する。`validate_scores` はnot-comparableおよびmissing/stale/not-applicable/not-evaluableのweightを0に限定しdependency root重複加点を拒否する。`validate_scenarios` は共通確率、total return（配当1回）、期待return、downside/permanent-loss確率を再計算する。`validate_selection` はhard gate、排他分類、ranking winner、絶対benchmark、NO_SELECTION、evidence/contrary evidenceを再検証する。
