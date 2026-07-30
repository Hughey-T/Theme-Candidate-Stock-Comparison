# Data contract

Candidate canonical identityはcandidate_id、issuer_id/name、ticker、exchange、share class、ADR、underlying security、former tickers、corporate-action lineage、listing countryの全Schema identity fieldであり、配列はsortしてcandidate集合もorder-independentにhashする。いずれかが変わればcandidate-set IDが変わる。

Phase artifactはmode/phase discriminator付き12-way `oneOf`。envelopeとpayloadはclosedで、Phase固有keyがrequired。evidence itemはID、statement、source type、as-of、judgment itemはevidence/contrary evidence、confidence、assumptions、invalidation conditionsを必須とする。Candidate分類はPRIMARY/SECONDARY/CONDITIONAL/WATCH/EXCLUDED、overall decisionはSELECTION/NO_SELECTIONである。
