# Update and handoff contract

任意のcomplete generation（initialまたはupdate）から次のupdateを開始できる。Update startは未使用generation ID、activeと一致するprevious generation、単調非減少comparison as-of、新しいsource cutoffを要求する。Generation historyは上書きしない。

Update Phase 1はprevious/updated/added/removed/retained detailed candidates、normalized identities、updated candidate-set ID、change reasons、recursive diffを保持する。Updated detailed candidatesがそのgenerationのcanonical comparison setとなり、Update Phase 2のmetrics、5 rankings/scores、scenarios、gates、classifications、handoff coverageを拘束する。

Update Phase 2はselectionを再計算し、new handoff ID未使用、active generation/set、old active IDとのsupersedes、decisionと全classification集合を検証する。同じatomic state writeでoldをsuperseded、新handoffをactiveにする。更新payloadに新しい分析詳細がないfieldは直前のvalidated handoffから決定的に継承し、新candidateはnot_evaluable/no_identified_catalyst stateで表す。
