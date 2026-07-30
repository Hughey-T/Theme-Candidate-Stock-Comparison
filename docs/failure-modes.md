# Failure modes

Terminal stop: generation取得不能/破損、404以外のlatest障害、Schema/semantic/hash不整合、mixed generation/set/cutoff、将来情報、TOCTOU byte変化、oversize、part異常、候補identity衝突、確率/期待値/順位改変。push失敗はgenerated_not_persisted、push後はpersisted_pending_verification、remote byte一致後だけintegrity_verified。失敗を公開済みと表示しない。
