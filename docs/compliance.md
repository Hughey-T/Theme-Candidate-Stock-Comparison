# Compliance matrix

| Requirement | Implementation | Contract | Executable tests |
|---|---|---|---|
| Windows-safe packaged schemas | `schema_runtime.schema_bytes` | `src/theme_compare/schemas`, no symlink | wheel outside-checkout CI, regeneration test |
| 12 closed Phase payloads | generator `phase_contracts` | phase-artifact `oneOf` | recursive closure, 12 valid, unknown/empty/type tests |
| Detailed-candidate coverage | `phase_validation.exact` and Phase 10 coverage | Phase 2–10 arrays/maps | duplicate/missing/unknown coverage mutations |
| Complete comparability matrix | normalized undirected pair/metric keys | Phase 2 matrix | duplicate/reverse/self/unknown/missing tests |
| Mandatory semantics/history | dispatcher + `StateMachine._validate_generation_history` | state/phase schemas | 10+2 E2E, old generation tampering |
| Strict JSON/finite | `models.strict_json_loads`, recursive finite checks | numeric constraints | NaN/Infinity/duplicate key/UTF-8 mutations |
| Evidence registry | `validate_evidence`, payload-ref walker | const evidence classes | wrong class/reference/duplicate/future mutations |
| Scenario and selection | `validate_scenarios`, initial/update selection dispatcher | Phase 7/10/Update 2 | annualized/weighted/month/ranking/classification mutations |
| Automatic handoff lifecycle | StateMachine initial activation/update application | handoff/session state | Update E2E asserts old superseded/new active |
| Typed handoff maps | generated handoff Schema + state coverage | fixed rankings/scenarios and typed candidate maps | handoff coverage mutations |
| Exact publication | `publish/reconstruct` | publication manifest | missing/modified manifest, inventory/path/hash tests |
| Reproducible CI | constraints + workflow | package resources | 3.11–3.13, quality, mutation, wheel E2E |
