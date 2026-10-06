# ui/pages/readme.py
"""README ページ — プロジェクト概要・図・構成・技術スタック。"""

from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_DIAGRAM_DIR = os.path.join(_ROOT, "docs", "diagrams")

st.set_page_config(page_title="README — DynamoDB RAG PoC", page_icon="📖", layout="wide")

st.markdown("# 📖 DynamoDB RAG PoC")
st.caption("AWS DynamoDB 公式ドキュメント（JA/EN）を対象に 4 種類のデータソースで RAG 精度を比較検証する PoC")

# ── 概要テーブル ──────────────────────────────────────
st.markdown("## 🎯 概要")
st.markdown("""
4 種類の**完全独立**した RAG パイプラインを `asyncio` で並列実行し、同一質問に対する回答品質を横並び比較します。

| ソース | 技術 | 検索方式 |
|---|---|---|
| 🟠 PostgreSQL | pgvector (pg17) | コサイン類似度ベクター検索 |
| 🟡 MySQL | FULLTEXT INDEX (8.0) | BM25 相当キーワード検索 |
| 🟢 Qdrant | qdrant:latest | 純粋コサイン類似度検索 |
| 🌐 WebFetch | OpenAI web_search | リアルタイム Web 検索 |

各パイプラインは **QueryAnalyzer → Retriever → Evaluator（max 3 回再検索）→ Ranker → Generator** の 5 ステップを独立実行します。
""")

st.divider()
st.markdown("## 🏗️ 図")

tab_arch, tab_seq, tab_flow = st.tabs(["System Architecture", "Sequence Diagram", "Data Flow"])

with tab_arch:
    st.markdown("""
```mermaid
graph TD
    U[👤 User] --> UI[🖥️ Streamlit UI]
    UI -->|POST /query| API[⚡ FastAPI + SSE]
    API -->|SSE stream| UI
    API -->|asyncio parallel| P1 & P2 & P3 & P4
    subgraph P1["Pipeline 1: PostgreSQL"]
        direction LR
        QA1[①QA]-->R1[②pgvector]-->E1[③Eval]-->RK1[④Rank]-->G1[⑤Gen]
    end
    subgraph P2["Pipeline 2: MySQL"]
        direction LR
        QA2[①QA]-->R2[②FULLTEXT]-->E2[③Eval]-->RK2[④Rank]-->G2[⑤Gen]
    end
    subgraph P3["Pipeline 3: Qdrant"]
        direction LR
        QA3[①QA]-->R3[②cosine]-->E3[③Eval]-->RK3[④Rank]-->G3[⑤Gen]
    end
    subgraph P4["Pipeline 4: WebFetch"]
        direction LR
        QA4[①QA]-->R4[②web]-->E4[③Eval]-->RK4[④Rank]-->G4[⑤Gen]
    end
    R1---PG[(PostgreSQL)]
    R2---MY[(MySQL)]
    R3---QD[(Qdrant)]
    R4---OAI[OpenAI API]
```
""")
    _f = os.path.join(_DIAGRAM_DIR, "architecture.drawio")
    if os.path.exists(_f):
        st.download_button("📥 architecture.drawio", open(_f).read(), "architecture.drawio", "application/xml")

with tab_seq:
    st.markdown("""
```mermaid
sequenceDiagram
    participant U as 👤 User
    participant UI as Streamlit
    participant API as FastAPI
    participant CH as RAG Chain ×4
    participant DB as DB / OpenAI
    U->>UI: ① 質問入力
    UI->>API: ② POST /query
    API->>CH: ③ asyncio.create_task ×4
    loop 各パイプライン独立
        CH->>CH: ④ QueryAnalyze
        CH-->>UI: SSE: query_analyze
        CH->>DB: ⑤ Retrieve
        DB-->>CH: docs
        CH-->>UI: SSE: retrieve
        CH->>CH: ⑥ Evaluate
        Note over CH: insufficient → retry max3
        CH-->>UI: SSE: evaluate
        CH->>CH: ⑦ Rank Top-K
        CH->>DB: ⑧ Generate 新規session
        DB-->>CH: final_answer
        CH-->>UI: SSE: generate
    end
    API-->>UI: ⑨ SSE result
    UI->>U: ⑩ 4カラム表示
```
""")
    _f = os.path.join(_DIAGRAM_DIR, "sequence.drawio")
    if os.path.exists(_f):
        st.download_button("📥 sequence.drawio", open(_f).read(), "sequence.drawio", "application/xml")

with tab_flow:
    st.markdown("""
```mermaid
flowchart LR
    SRC["AWS Docs JA+EN"] --> CRAWL["🕷️ Crawler"]
    CRAWL --> CHUNK["✂️ Chunker 512t/50"]
    CHUNK -->|metadata| MY[(MySQL)]
    CHUNK --> EMBED["🔢 Embedder"]
    EMBED -->|doc+emb| PG[(PostgreSQL)]
    EMBED -->|vectors| QD[(Qdrant)]
    Q["❓ Question"] --> QA["QueryAnalyzer ×4"]
    QA --> R1["pgvector"] --> PG
    QA --> R2["FULLTEXT"] --> MY
    QA --> R3["Qdrant"] --> QD
    QA --> R4["web_search"] --> OAI[OpenAI]
    R1 & R2 & R3 & R4 -->|Top-K| GEN["Generator ×4"]
    GEN --> OUT["💬 Final Answer ×4"]
```
""")
    _f = os.path.join(_DIAGRAM_DIR, "dataflow.drawio")
    if os.path.exists(_f):
        st.download_button("📥 dataflow.drawio", open(_f).read(), "dataflow.drawio", "application/xml")

# ── ディレクトリ構成 ──────────────────────────────────
st.divider()
st.markdown("## 📁 ディレクトリ構成")
st.code("""
applications/2026-10-06-rags/
├── memory-bank/          # Memory Bank（設計・進捗管理）
├── data/                 # ① データ収集
│   ├── sources.py        #   収集 URL 定義（JA/EN 個別ページ）
│   ├── crawler.py        #   requests + BeautifulSoup4（meta-refresh 対応）
│   ├── chunker.py        #   512 tokens / 50 overlap
│   ├── postgres_loader.py / mysql_loader.py / qdrant_loader.py
│   └── run_all.py        #   一括実行エントリーポイント
├── pipeline/             # ② 4本独立 RAG パイプライン
│   ├── models.py         #   共有 Pydantic モデル (StepLog 等)
│   ├── step_logger.py    #   LangChain AsyncCallback → SSE ログ
│   ├── query_analyzer.py #   ソース別プロンプト生成
│   ├── evaluator.py      #   十分性判定 + 再検索ループ
│   ├── ranker.py         #   Top-K 選定
│   ├── generator.py      #   最終回答生成（新規 session）
│   ├── rag_chain.py      #   asyncio 並列オーケストレーター
│   └── retrievers/       #   postgres / mysql / qdrant / web
├── api/                  # FastAPI + SSE (POST /query)
├── ui/
│   ├── app.py            #   メイン（質問バー上部 + 4カラム）
│   ├── pages/readme.py   #   本ページ (/readme)
│   └── components/       #   settings_panel / step_renderer
├── docs/diagrams/        #   architecture / sequence / dataflow .drawio
├── tests/
├── docker-compose.yml    #   PostgreSQL + MySQL + Qdrant
└── pyproject.toml
""", language="text")

# ── 技術スタック ──────────────────────────────────────
st.divider()
st.markdown("## 🛠️ 技術スタック")
st.markdown("""
| レイヤー | 技術 | 備考 |
|---|---|---|
| UI | Streamlit ≥1.40 | `st.columns([1,2,2,2,2])` 5分割 |
| API | FastAPI + SSE | `StreamingResponse` 非同期ストリーム |
| RAG | LangChain ≥0.3 | 独立 `Runnable` + `asyncio` 並列 |
| Document DB | PostgreSQL 17 + pgvector 0.8 | `pgvector/pgvector:pg17` |
| RDB Index | MySQL 8.0 | FULLTEXT INDEX ngram parser |
| Vector DB | Qdrant latest | `qdrant/qdrant` Docker |
| Embedding | text-embedding-3-small | OpenAI API |
| LLM | gpt-4o（UI で切替可）| OpenAI API |
| Crawler | requests + BeautifulSoup4 | meta-refresh リダイレクト対応 |
| Container | Docker Compose | ローカル完結 |
| Python | 3.13 | pyproject.toml + pip |
""")

# ── 参照リソース ──────────────────────────────────────
st.divider()
st.markdown("## 🔗 参照リソース")
st.markdown("""
- [DynamoDB Developer Guide (JA)](https://docs.aws.amazon.com/ja_jp/amazondynamodb/latest/developerguide/)
- [DynamoDB Data Modeling Guide (JA)](https://docs.aws.amazon.com/ja_jp/prescriptive-guidance/latest/dynamodb-data-modeling/)
- [DynamoDB Developer Guide (EN)](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/)
- [AWS Database Blog – DynamoDB](https://aws.amazon.com/blogs/database/category/database/amazon-dynamodb/)
- [LangChain Docs](https://python.langchain.com/)
- [Qdrant Docs](https://qdrant.tech/documentation/)
- [pgvector](https://github.com/pgvector/pgvector)
""")

