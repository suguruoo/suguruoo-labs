# ■ Whatisthis

個人における学習サイクルを支えるパイプラインにおける、input を蓄積する Notes。

```
                   ┌──────────────┐
                   │    Input     │
                   │ Docs / Web / │
                   │ LLM / Idea   │
                   └──────┬───────┘
                          ↓
                 suguruoo-notes
                          │
                     inbox/
                          │
                          ↓
                     organized
                          │
              ┌───────────┴──────────┐
              ↓                      ↓
        suguruoo-labs          suguruoo-docs
              │                      ↑
          experiment                 │
              │                      │
              └──── findings ────────┘
```            

## ● directry-rules

カテゴリーごとにファイル形式においては hive 形式の
`2026-09-27` + `hoober` .md
でファイルを作成する。

それぞれのファイル/プロジェクトにおいて README.md に以下のフラグを張る。

```md
title: 
date: 
type: []
tags: []
```

## ● document-rules

input において使用したドキュメントや reference の参照は必ず明らかにするものとして、理解や推測と分離をする。
使用したリソースはクリーンアップすることが許されるが、必ず再現可能な情報を CLI コマンドや、スクリプト含めて残す。

ドキュメントや reference が存在する場合にその出典を必ず明確にする。
LLM の生成したものをデータソースとして利用しない。