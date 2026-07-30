# Compliance matrix

| Requirement | Implementation | Schema | Executable tests |
|---|---|---|---|
| RFC3339 UTC instant | `models.parse_rfc3339`, `validate_envelope` | datetime pattern/format | offset/future/timezone tests |
| Canonical candidate identity | `models.candidate_set_id` | candidate schemas | seven identity mutations/order test |
| 12 closed Phase contracts | `schema_runtime`, `StateMachine.command` | phase-artifact oneOf/session embedded items | payload swap/unknown/malformed judgment |
| Five derived rankings | `ranking.derive_rankings/validate_stored_rankings` | ranking | score/order/tie/coverage mutations |
| Scenario/horizon returns | `engine.derive_scenario_results` | common scenario | TSR/annualization/zero months |
| Selection/NO_SELECTION | `engine.select_from_analysis`, `validate_selection` | final-selection/handoff | hard gate/no-selection/selection mutations |
| Update/history/handoff | `StateMachine`, `engine.update_diff` | state/update-diff/handoff | generation preservation/nested ID diff/supersession |
| Atomic publication | `publication.publish/reconstruct` | publication manifest | UTF-8, retry, unknown/traversal/duplicate/hash mutations |
| Persistence/latest | `transition_persistence/update_latest` | persistence enum | skip/repeat/unverified latest tests |
| Reproducible CI | `constraints-dev.txt`, workflow | regenerated Schema | full matrix/quality/fresh clone jobs |
