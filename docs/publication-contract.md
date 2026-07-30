# Publication contract

`generations/<generation>/` はimmutable。manifestはschema/generation/candidate-set/cutoff/created-at、完全inventory、raw SHA-256、canonical SHA-256、byte size、sequence、part count、verification statusを持つ。part上限48,000 bytes。欠落、重複、順序、別generation、size/hash、復元canonical hashを検査する。latestの404だけが明示的取得経路変更を許し、破損・検証失敗で旧Schemaへfallbackしない。remote byte検証前はintegrity_verifiedにしない。
