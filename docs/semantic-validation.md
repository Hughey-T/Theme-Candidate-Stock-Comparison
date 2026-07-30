# Semantic validation

StateMachineはstate Schema/semantic→artifact Schema→phase dispatcher→cross-phase checks→result state Schema/semantic→atomic writeの順で実行する。DispatcherはPhase 1 candidate identity/set/limits、Phase 2 matrix coverage、Phase 7 scenario derivations、Phase 10 atomic metric rankingsとPhase 7一致、Update 1 generation lineage、Update 2 handoff supersessionを検証する。

Scenario validatorはcurrent/target price、dividend、realization monthsだけからTSRとannualized returnを再計算し、weighted total/annualized return、expected months、downside/permanent-loss probabilityを照合する。Evidence validatorは分類、ID一意性、cutoff以前、support/contrary reference実在を検証する。
