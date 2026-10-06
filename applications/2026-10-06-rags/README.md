title: DynamoDB RAG PoC
date: 2026-10-06
type: [experiment, rag, llm]
tags: [dynamodb, rag, langchain, postgresql, mysql, qdrant, openai, streamlit]

# DynamoDB RAG PoC

AWS DynamoDB 公式ドキュメント（日本語・英語）を対象に、4種類のデータソース（PostgreSQL Document DB / MySQL RDB Index / Qdrant Vector DB / Natural WebFetch）を使った RAG の精度を比較検証する PoC。

## ディレクトリ構成

```
applications/2026-10-06-rags/
├── memory-bank/          # Memory Bank（設計・進捗管理）
├── data/                 # ① データ収集スクリプト
├── pipeline/             # ② 4本独立 RAG パイプライン
├── api/                  # FastAPI + SSE エンドポイント
├── ui/                   # Streamlit UI
├── tests/                # ユニットテスト
├── docker-compose.yml    # PostgreSQL / MySQL / Qdrant
├── pyproject.toml        # 依存管理
└── .env.example          # 環境変数テンプレート
```

## セットアップ

```bash
# 1. 環境変数設定
cp .env.example .env
# .env に OPENAI_API_KEY を設定

# 2. DB 起動
docker compose up -d

# 3. 依存インストール
pip install -e ".[dev]"

# 4. データ収集
python -m data.run_all

# 5. API 起動
uvicorn api.main:app --reload --port 8000

# 6. UI 起動
streamlit run ui/app.py
```

## 参照リソース

- [DynamoDB Developer Guide (JA)](https://docs.aws.amazon.com/ja_jp/amazondynamodb/latest/developerguide/)
- [DynamoDB Data Modeling (JA)](https://docs.aws.amazon.com/ja_jp/prescriptive-guidance/latest/dynamodb-data-modeling/)
- [DynamoDB Developer Guide (EN)](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/)
- [AWS Database Blog](https://aws.amazon.com/blogs/database/)

