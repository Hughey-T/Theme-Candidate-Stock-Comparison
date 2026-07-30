# Compliance matrix

|要求|実装|Schema|テスト|
|---|---|---|---|
|10+2 Phase/2操作/再開|`StateMachine.command/load`|session-state|`test_initial_ten_phases_and_idempotency_guard`, `test_update_two_phases`, transition/resume tests|
|identity/12→8→5→2|`validate_candidates`, phase contract|candidate-input, normalized-candidate|candidate mutation tests|
|共通scenario/再計算|`derive_scenario_results`, `validate_scenarios`|common-scenario|scenario/nonfinite tests|
|比較不能/double count|`validate_scores`|ranking|unusable/dependency tests|
|hard gate/NO_SELECTION|`classify`, `validate_selection`|final-selection|hard-gate/no-selection tests|
|handoff|`build_handoff`|handoff|selection and E2E paths|
|generation/cutoff|`validate_envelope`|phase-artifact|mixed envelope/timezone tests|
|publication/hash/parts|`publish/reconstruct`|publication-manifest|publication mutation tests|
|update diff/history|`update_diff`, state update|update-diff|diff/update tests|
|closed schema/enums|schema generator/constants|全10 Schema|schema-current/closed/unknown tests|
|サンプル/CI|samples, workflow|該当Schema|sample catalogue, full pytest matrix|
