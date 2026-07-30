# Architecture

入力 → closed Schema → semantic validator → persisted StateMachine → one Phase artifact → immutable publisher、の一方向構成である。Phase開始時にstateと既存artifactsをdiskから再取得し envelopeを検証する。Phase 7が共通 THEME_BEAR/BASE/BULL を固定し、Phase 10が入力値から期待値・損失確率・順位・分類を再導出してhandoffを作る。latestは便宜的pointerに過ぎず、開始後は固定generation directoryだけを読む。
