# Data contract

Candidate canonical identityはcandidate_id、issuer_id/name、ticker、exchange、share class、ADR、underlying security、former tickers、corporate-action lineage、listing countryの全Schema identity fieldであり、配列と候補集合をsortしてhashする。

Phase artifactはmode/phase discriminator付き12-way `oneOf`。各branch、payload wrapper、Phase固有object、evidence/judgment itemはclosedで、空placeholderでは完了できない。Phase 1はtheme/hypothesis/as-of/cutoff/candidates/data states/exclusions/limits、Phase 2はbusiness modelとcomparability matrix、Phase 3–9はphase contract記載の評価・財務・valuation・scenario・catalyst・risk成果物、Phase 10はatomic metrics/5 rankings/scenarios/gates/classifications/overall decision/benchmarks/risk limits/handoffを必須とする。Update 1はold/new generationとrecursive diff、Update 2はranking/classification changesとhandoff supersessionを必須とする。

FACTS、COMPANY_CLAIMS、EXTERNAL_ESTIMATESはそれぞれsource_type constを持つ。Judgmentは存在するsupport/contrary evidence ID、confidence、assumptions、invalidation conditionsが必須である。Schema正本は`src/theme_compare/schemas`のpackage resourcesで、root `schemas`は同じdirectoryへのsymlink、generatorだけが更新する。
