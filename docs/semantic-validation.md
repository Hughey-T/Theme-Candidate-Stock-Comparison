# Semantic validation

Schema通過後、candidate identity/set hash、timezone-aware UTC instants、generation/set/cutoff、scenario probability、TSR、annualized return、expected months、downside/permanent lossを再計算する。Rankingはapplicability→state→comparability→dependency-root dedup→weighted normalized score→candidate-id tie breakの順でcompany_quality/tactical/structural/risk_adjusted/portfolio_fitを独立導出し、保存score/orderと一致させる。Selectionはrisk-adjusted ranking、annualized scenario return、同期間cash/investment benchmark、hard gate、downside/permanent-loss limitから再計算する。
