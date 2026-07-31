# Test matrix

Schema testsは全12 branchesとnested closure、Phase固有required/type/empty/countを検証する。Semantic mutationsはcandidate coverage、comparability pair/metric、ranking/score/selection、payload evidence、NaN/Infinity/duplicate JSON key/invalid UTF-8、scenario annualizationを扱う。State E2EはInitial 10→new as-of/cutoff Update 2と自動handoff supersessionを実行し、旧generation artifact/cutoff/set改変を拒否する。

Publication testsはUTF-8/base64、atomic retry、missing/modified/schema-invalid manifest、exact inventory、missing/extra/duplicate/path/hash、terminal persistence/latestを扱う。CIはconstraints固定の3.11/3.12/3.13 full pytest、quality/schema mutation、symlinkなしpackage resourceのrepository外wheel importを実行する。

Update mutation matrixはold/new generation metadataの6項目、field別state enum、unchanged/changed/added/removed/unavailableとvalueの矛盾、catalystの空/非空、evidence deltaの不整合を含む。
