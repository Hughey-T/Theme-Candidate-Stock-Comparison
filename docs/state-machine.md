# State machine

`initial:1..10`と`update:1..2`だけを許す。全commandはstate bytes decode、packaged Schema、state semantic、artifact Schema、evidence/phase/cross-phase semantic dispatcher、transition、result Schema/semantic、atomic writeを通る。

Update startはclosed `update-start` metadataとしてnew generation/candidate-set/comparison-as-of/source-cutoff/previous generationを要求する。New cutoffはnew as-of以下、new as-ofはold as-of以降、same generationと暗黙のstale cutoff再利用を拒否する。generation_history entryごとにas-of/cutoff/artifactsを保持し、active stateだけをnew generationへ切替える。
