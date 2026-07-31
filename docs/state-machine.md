# State machine

`initial:1..10`と各`update:1..2`を許し、complete updateからさらにupdateを開始できる。全commandはstrict state bytes decode、packaged Schema、全generation history semantic、artifact Schema、evidence/phase/cross-phase semantic、transition、result validation、1回のatomic writeを通る。

Initial Phase 10でactual Phase 6/8/9およびevidence/judgmentからactive handoffを投影する。各Update Phase 2はselectionとhandoff identity/classificationを照合し、同じtransaction内でoldへsuperseded_by/invalidated_at/reasonを設定、新handoffをactiveとして追加し、deduplicated superseded IDsを更新する。
