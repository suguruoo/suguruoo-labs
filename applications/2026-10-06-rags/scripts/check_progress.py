#!/usr/bin/env python3
# scripts/check_progress.py
"""データ収集の進捗を各DBに問い合わせて確認するスクリプト。

Usage:
    PYTHONPATH=. .venv/bin/python scripts/check_progress.py
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def check_postgres() -> None:
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            user=os.environ.get("POSTGRES_USER", "raguser"),
            password=os.environ.get("POSTGRES_PASSWORD", "ragpass"),
            dbname=os.environ.get("POSTGRES_DB", "ragdb"),
        )
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents;")
            total = cur.fetchone()[0]
            cur.execute("SELECT lang, COUNT(*) FROM documents GROUP BY lang;")
            by_lang = cur.fetchall()
            cur.execute("SELECT source_type, COUNT(*) FROM documents GROUP BY source_type;")
            by_type = cur.fetchall()
        conn.close()
        print(f"[PostgreSQL] total chunks: {total}")
        for row in by_lang:
            print(f"  lang={row[0]}: {row[1]}")
        for row in by_type:
            print(f"  source_type={row[0]}: {row[1]}")
    except Exception as e:
        print(f"[PostgreSQL] error: {e}")


def check_mysql() -> None:
    try:
        import pymysql
        conn = pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "localhost"),
            port=int(os.environ.get("MYSQL_PORT", "3306")),
            user=os.environ.get("MYSQL_USER", "raguser"),
            password=os.environ.get("MYSQL_PASSWORD", "ragpass"),
            database=os.environ.get("MYSQL_DB", "ragdb"),
            charset="utf8mb4",
        )
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents;")
            total = cur.fetchone()[0]
            cur.execute("SELECT lang, COUNT(*) FROM documents GROUP BY lang;")
            by_lang = cur.fetchall()
        conn.close()
        print(f"[MySQL] total chunks: {total}")
        for row in by_lang:
            print(f"  lang={row[0]}: {row[1]}")
    except Exception as e:
        print(f"[MySQL] error: {e}")


def check_qdrant() -> None:
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(
            host=os.environ.get("QDRANT_HOST", "localhost"),
            port=int(os.environ.get("QDRANT_PORT", "6333")),
        )
        collection = os.environ.get("QDRANT_COLLECTION", "dynamodb_docs")
        info = client.get_collection(collection)
        print(f"[Qdrant] collection={collection} vectors_count={info.vectors_count}")
    except Exception as e:
        print(f"[Qdrant] error: {e}")


if __name__ == "__main__":
    print("=== Data Collection Progress ===")
    check_postgres()
    check_mysql()
    check_qdrant()
