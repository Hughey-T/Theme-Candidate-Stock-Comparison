# Test matrix

Schema closureは通常objectのtop-levelとnested property objects、oneOfの全12 branchesを再帰検査する。各Phaseの実payloadをvalid fixtureとし、unknown/required/type/wrong-phase/empty/count/incomplete Phase 10をmutationする。Semantic testsはidentity、offset時系列、evidence class/reference/duplicate/future、scenario annualized/weighted/months、ranking score/order/tie、selection/benchmark、nested diffを扱う。

State E2EはInitial 10→new as-of/cutoff Update 2を実行し、same generation/stale/future/old timeを拒否する。Publication testsはUTF-8/base64、atomic retry、missing/modified/schema-invalid manifest、missing/extra/duplicate/path/hash、terminal persistence/latestを扱う。CIはconstraints固定の3.11/3.12/3.13 full pytest、quality/schema mutation、repository外wheel importとStateMachine resource loadを実行する。
