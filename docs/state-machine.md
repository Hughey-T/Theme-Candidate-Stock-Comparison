# State machine

`initial:1..10` と `update:1..2` のみ。`次`はartifact phaseがcurrent phaseと一致する場合だけatomic writeし、飛越し・逆行・再実行を拒否する。initial complete前の`更新`、update中の`更新`を拒否する。更新には異なるgenerationを要求し履歴は上書きせず新generationへ結び付ける。statusとpersistence statusは独立である。
