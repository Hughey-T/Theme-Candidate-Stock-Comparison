# Compliance matrix

| Requirement | Implementation | Contract | Executable tests |
|---|---|---|---|
| Repeated updates | `StateMachine.command` complete-generation transition | update-start | initial→g2→g3 E2E and handoff chain assertions |
| Update candidate set/context | Update Phase 1 dispatcher/detail history | candidate deltas + changed/unchanged/not-evaluable context | added/removed/retained/identity/set coverage |
| Actual handoff projection | `_project_handoff_context` change overlay | typed handoff/update context states | g1=10→g2=12→g3=12 valuation/catalyst/risk E2E |
| Update handoff equality | Update Phase 2 dispatcher/application | updated-selection | decision/classification/identity/reuse/supersession tests |
| Historical update validation | `_validate_generation_history` replay context | state/phase schemas | g2 tampering after g3 mutation test |
| Strict publication JSON | `strict_json_loads` at manifest/part/payload | publication manifest | duplicate/NaN/UTF-8/malformed mutations per layer |
| Windows-safe packaged schemas | `schema_runtime.schema_bytes` | `src/theme_compare/schemas`, no symlink | wheel outside-checkout CI |
| Candidate/matrix coverage | `phase_validation.exact` + normalized pair keys | Phase 2–10 | duplicate/missing/unknown/reverse/self mutations |
| Reproducible CI | constraints + workflow | 11 packaged schemas/12 contracts | 3.11–3.13, quality, 130-test suite, wheel E2E |
