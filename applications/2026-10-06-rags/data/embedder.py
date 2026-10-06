# data/embedder.py
"""ローカル embedding モジュール。

sentence-transformers の multilingual-e5-large を使い、
OpenAI API を呼ばずに完全ローカルで embedding を生成する。

初回実行時に HuggingFace Hub からモデルをダウンロードする（約 2GB）。
以降は ~/.cache/huggingface/ のキャッシュを使用する。
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# multilingual-e5-large:
#   - 次元数: 1024
#   - 日英両対応・高精度
#   - MIT ライセンス
LOCAL_MODEL_NAME = "intfloat/multilingual-e5-large"
EMBEDDING_DIM = 1024

# e5 シリーズはクエリに "query: " プレフィックス、ドキュメントに "passage: " プレフィックスが必要
_PASSAGE_PREFIX = "passage: "
_QUERY_PREFIX = "query: "


@lru_cache(maxsize=1)
def _get_model():
    """SentenceTransformer モデルをシングルトンで返す。

    Returns:
        SentenceTransformer インスタンス。
    """
    from sentence_transformers import SentenceTransformer

    logger.info("Loading local embedding model: %s", LOCAL_MODEL_NAME)
    model = SentenceTransformer(LOCAL_MODEL_NAME)
    logger.info("Model loaded. Embedding dim: %d", model.get_sentence_embedding_dimension())
    return model


class LocalEmbedder:
    """ローカル sentence-transformers による embedding 生成クラス。

    データ収集時（passage）とクエリ時（query）でプレフィックスを切り替える。
    """

    @staticmethod
    def embed_passages(texts: list[str]) -> list[list[float]]:
        """ドキュメント（passage）のバッチ embedding を生成する。

        データ収集・DB格納時に使用する。

        Args:
            texts: ドキュメントテキストのリスト。

        Returns:
            embedding ベクターのリスト。
        """
        model = _get_model()
        prefixed = [_PASSAGE_PREFIX + t for t in texts]
        embeddings = model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()

    @staticmethod
    def embed_query(text: str) -> list[float]:
        """クエリ（query）の embedding を生成する。

        RAG 検索時に使用する。

        Args:
            text: 検索クエリテキスト。

        Returns:
            embedding ベクター。
        """
        model = _get_model()
        prefixed = _QUERY_PREFIX + text
        embedding = model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
        return embedding.tolist()

    @staticmethod
    def embed_batch(texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """passage embedding をバッチ分割して生成する（大量データ対応）。

        Args:
            texts: テキストのリスト。
            batch_size: 1バッチのサイズ。

        Returns:
            embedding ベクターのリスト。
        """
        model = _get_model()
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            prefixed = [_PASSAGE_PREFIX + t for t in batch]
            embeddings = model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
            all_embeddings.extend(embeddings.tolist())
            logger.debug("embedded batch %d-%d / %d", i, i + len(batch), len(texts))
        return all_embeddings
