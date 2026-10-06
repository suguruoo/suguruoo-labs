# data/run_all.py
"""全データ収集・ロードを一括実行するエントリーポイント。

Usage:
    python -m data.run_all
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from data.chunker import chunk_pages
from data.crawler import crawl_all
from data.mysql_loader import init_schema as mysql_init
from data.mysql_loader import load_chunks as mysql_load
from data.postgres_loader import init_schema as pg_init
from data.postgres_loader import load_chunks as pg_load
from data.qdrant_loader import init_collection as qdrant_init
from data.qdrant_loader import load_chunks as qdrant_load

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _load_env() -> dict[str, str]:
    """環境変数を読み込んで設定辞書を返す。"""
    load_dotenv()

    # .secrets ファイルからも読む
    secrets_path = os.path.join(os.path.dirname(__file__), "..", ".secrets")
    if os.path.exists(secrets_path):
        with open(secrets_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    key = key.strip().strip('"')
                    val = val.strip().strip('"')
                    os.environ.setdefault(key, val)

    openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_SECRET_KEY")
    # embedding はローカルモデルを使うため、OpenAI key は LLM（RAG クエリ時）のみ必要
    # データ収集フェーズでは不要なので警告のみ
    if not openai_key:
        logger.warning("OPENAI_API_KEY が未設定です（データ収集は不要。RAGクエリ時に必要）")

    return {
        "openai_api_key": openai_key or "",
        "pg_host": os.environ.get("POSTGRES_HOST", "localhost"),
        "pg_port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "pg_user": os.environ.get("POSTGRES_USER", "raguser"),
        "pg_password": os.environ.get("POSTGRES_PASSWORD", "ragpass"),
        "pg_dbname": os.environ.get("POSTGRES_DB", "ragdb"),
        "mysql_host": os.environ.get("MYSQL_HOST", "localhost"),
        "mysql_port": int(os.environ.get("MYSQL_PORT", "3306")),
        "mysql_user": os.environ.get("MYSQL_USER", "raguser"),
        "mysql_password": os.environ.get("MYSQL_PASSWORD", "ragpass"),
        "mysql_database": os.environ.get("MYSQL_DB", "ragdb"),
        "qdrant_host": os.environ.get("QDRANT_HOST", "localhost"),
        "qdrant_port": int(os.environ.get("QDRANT_PORT", "6333")),
        "qdrant_collection": os.environ.get("QDRANT_COLLECTION", "dynamodb_docs"),
    }


def main() -> None:
    """全データ収集・ロードを実行する。"""
    cfg = _load_env()

    # --- Step 1: スキーマ初期化 ---
    logger.info("=== Step 1: DB スキーマ初期化 ===")
    pg_settings = {
        "host": cfg["pg_host"],
        "port": cfg["pg_port"],
        "user": cfg["pg_user"],
        "password": cfg["pg_password"],
        "dbname": cfg["pg_dbname"],
    }
    mysql_settings = {
        "host": cfg["mysql_host"],
        "port": cfg["mysql_port"],
        "user": cfg["mysql_user"],
        "password": cfg["mysql_password"],
        "database": cfg["mysql_database"],
    }
    pg_init(pg_settings)
    mysql_init(mysql_settings)
    qdrant_init(cfg["qdrant_host"], cfg["qdrant_port"], cfg["qdrant_collection"])

    # --- Step 2: クロール ---
    logger.info("=== Step 2: クロール ===")
    pages = crawl_all()
    if not pages:
        logger.error("クロール結果が0件です。URLを確認してください。")
        sys.exit(1)

    # --- Step 3: チャンキング ---
    logger.info("=== Step 3: チャンキング ===")
    chunks = chunk_pages(pages)
    logger.info("合計 %d チャンク", len(chunks))

    # --- Step 4: PostgreSQL ロード ---
    logger.info("=== Step 4: PostgreSQL ロード (ローカルembedding) ===")
    pg_load(chunks, pg_settings)

    # --- Step 5: MySQL ロード ---
    logger.info("=== Step 5: MySQL ロード ===")
    mysql_load(chunks, mysql_settings)

    # --- Step 6: Qdrant ロード ---
    logger.info("=== Step 6: Qdrant ロード (ローカルembedding) ===")
    qdrant_load(
        chunks,
        host=cfg["qdrant_host"],
        port=cfg["qdrant_port"],
        collection_name=cfg["qdrant_collection"],
    )

    logger.info("=== 全データ収集・ロード完了 ===")


if __name__ == "__main__":
    main()
