# Data contract

Identityはcandidate_idに加えissuer_id、ticker、exchange、share_class、ADR/underlying、former ticker、corporate-action lineage、listing countryを保持する。FACTS、COMPANY_CLAIMS、EXTERNAL_ESTIMATES、JUDGMENTSを別配列に保存する。Judgmentは `judgment/evidence_refs/contrary_evidence_refs/confidence/assumptions/invalidation_conditions` 必須。data stateはconstantsの8 enum、comparabilityは4 enumを正本とする。日時はtimezone付きRFC 3339、価格・株式数は有限かつ非負（current price/sharesは正）、probabilityは0..1。
