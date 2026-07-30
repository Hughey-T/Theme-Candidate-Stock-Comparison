# Compliance matrix

| Requirement | Implementation | Contract | Executable tests |
|---|---|---|---|
| Packaged schemas | `schema_runtime.schema_bytes` | package data + generator | wheel outside-checkout CI, regeneration test |
| 12 closed Phase payloads | generator `phase_contracts` | phase-artifact `oneOf` | recursive closure, 12 valid, unknown/empty/wrong payload tests |
| Mandatory phase semantics | `phase_validation.validate_phase_artifact`, `StateMachine.command` | state/phase schemas | 10+2 E2E and mutation tests |
| UTC/as-of update | `parse_rfc3339`, update-start handling | update-start/session-state | offset, stale/same generation, new cutoff E2E |
| Evidence integrity | `validate_evidence` | const-classified evidence items | wrong class/reference/duplicate/future/removal mutations |
| Scenario derivation | `validate_scenarios` | Phase 7/10 scenario result | annualized/weighted/month mutations |
| Ranking and selection | ranking + Phase 10 dispatcher | Phase 10 atomic metrics/rankings/selection | score/order/gate/NO_SELECTION mutations |
| Exact publication | `publish/reconstruct` | publication manifest | missing/modified manifest, missing/extra/duplicate/path/hash tests |
| Persistence failure | transition/terminal_failure/latest | manifest status/failure metadata | invalid transition and latest tests |
| Reproducible CI | constraints + workflow | generated resources | 3.11–3.13, quality, schema/mutation, wheel E2E |
