# data/chunker.py
"""テキストチャンキングモジュール。

tiktoken で token 数を計測しながら固定サイズ + オーバーラップで分割する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import tiktoken

from data.crawler import CrawledPage

logger = logging.getLogger(__name__)

_ENCODING = "cl100k_base"  # text-embedding-3-small と同じエンコーダー
_CHUNK_SIZE = 512  # tokens
_CHUNK_OVERLAP = 50  # tokens


@dataclass
class Chunk:
    """1チャンク分のデータ。"""

    url: str
    lang: str
    source_type: str
    title: str
    section: str
    content: str
    chunk_index: int
    keywords: list[str]


def _split_tokens(text: str, encoding: tiktoken.Encoding) -> list[str]:
    """テキストをトークン数ベースでチャンク分割する。

    Args:
        text: 分割対象テキスト。
        encoding: tiktoken エンコーダー。

    Returns:
        チャンク文字列のリスト。
    """
    tokens = encoding.encode(text)
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + _CHUNK_SIZE, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(encoding.decode(chunk_tokens))
        if end == len(tokens):
            break
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


def chunk_pages(pages: list[CrawledPage]) -> list[Chunk]:
    """CrawledPage リストを Chunk リストに変換する。

    Args:
        pages: クロール結果のページリスト。

    Returns:
        チャンクリスト。
    """
    encoding = tiktoken.get_encoding(_ENCODING)
    all_chunks: list[Chunk] = []

    for page in pages:
        text_chunks = _split_tokens(page.content, encoding)
        for idx, chunk_text in enumerate(text_chunks):
            chunk = Chunk(
                url=page.url,
                lang=page.lang,
                source_type=page.source_type,
                title=page.title,
                section=page.section,
                content=chunk_text,
                chunk_index=idx,
                keywords=page.keywords,
            )
            all_chunks.append(chunk)

    logger.info(
        "chunk_pages done: %d pages → %d chunks",
        len(pages),
        len(all_chunks),
    )
    return all_chunks
