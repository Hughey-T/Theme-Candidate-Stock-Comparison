# Semantic validation

StateMachineはstate Schema/全generation history semantic→artifact Schema→generation evidence registry→payload evidence refs→phase dispatcher→cross-phase checks→transition→result state Schema/semantic→atomic writeの順で実行する。DispatcherはPhase 2の詳細候補をcanonical setとし、Phase 3～10のcandidate arrays/mapsをexact coverage（missing/unknown/duplicateなし）で照合する。Comparability matrixはundirected pairを正規化し、全pair×primary/secondary metrics、重複、逆向き矛盾、self/unknownを検証する。

Scenario validatorはcurrent/target price、dividend、realization monthsだけからTSRとannualized returnを再計算し、weighted total/annualized return、expected months、downside/permanent-loss probabilityを照合する。Initial Phase 10とUpdate Phase 2はいずれもatomic metricsからrankingを再導出し、scenario、benchmark、risk limit、hard gate、classification、overall decision、handoffを再検証する。
