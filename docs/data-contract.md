# Data contract

Candidate canonical identityはcandidate_id、issuer_id/name、ticker、exchange、share class、ADR、underlying security、former tickers、corporate-action lineage、listing countryの全Schema identity fieldであり、配列と候補集合をsortしてhashする。

Phase artifactはmode/phase discriminator付き12-way `oneOf`。各branch、payload wrapper、Phase固有object、evidence/judgment itemはclosedで、空placeholderでは完了できない。Phase 1はtheme/hypothesis/as-of/cutoff/candidates/data states/exclusions/limits、Phase 2はbusiness modelとcomparability matrix、Phase 3–9はphase contract記載の評価・財務・valuation・scenario・catalyst・risk成果物、Phase 10はatomic metrics/5 rankings/scenarios/gates/classifications/overall decision/benchmarks/risk limits/handoffを必須とする。Update 1はold/new generationとrecursive diff、Update 2はranking/classification changesとhandoff supersessionを必須とする。

FACTS、COMPANY_CLAIMS、EXTERNAL_ESTIMATESはそれぞれsource_type constを持つ。Judgmentは存在するsupport/contrary evidence ID、confidence、assumptions、invalidation conditionsが必須である。Schema正本は`src/theme_compare/schemas`のpackage resourcesで、root symlinkは使用せず、generatorだけがpackage resourceを更新する。

Handoff schema version 2ではconfidence/catalyst/risk/invalidationをclosed typed snapshotとし、operation stateとanalysis data stateを分離する。Candidate別assumption/evidence mapはcanonical candidate setを完全coverageし、global evidence manifestはglobal refsとcandidate refsの決定的unionである。

Initial handoffのevidenceはsource recordの`candidate_id`でpartitionする。null identityは`global_evidence_refs`、candidate identityは対応する`candidate_evidence_refs[candidate]`だけに入る。Candidate identityを持たないjudgment assumptionsはglobal `key_assumptions`にのみ保存し、candidate mapへ推測複製しない。
