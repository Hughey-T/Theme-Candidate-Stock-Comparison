# State machine

`initial:1..10`と`update:1..2`だけを許す。全commandはstrict state bytes decode、packaged Schema、全generation history、artifact Schema、evidence/phase/cross-phase semantic、transition、result validation、1回のatomic writeを通る。

Initial Phase 10でactive handoffを履歴へ登録する。Update Phase 2は同じtransaction内でold active handoffと`supersedes`/generationを照合し、oldへsuperseded_by/invalidated_at/reasonを設定、新handoffをactiveとして追加し、active IDとdeduplicated superseded IDsを更新する。外部の追加lifecycle呼出は不要である。
