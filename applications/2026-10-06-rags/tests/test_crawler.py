# tests/test_crawler.py
"""クローラーのユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from data.chunker import Chunk, chunk_pages
from data.crawler import CrawledPage, _clean_text, _extract_keywords, _extract_section
from data.sources import ALL_SOURCES, EN_SOURCES, JA_SOURCES


class TestSources:
    def test_ja_sources_not_empty(self) -> None:
        assert len(JA_SOURCES) > 0

    def test_en_sources_not_empty(self) -> None:
        assert len(EN_SOURCES) > 0

    def test_all_sources_combines_both(self) -> None:
        assert len(ALL_SOURCES) == len(JA_SOURCES) + len(EN_SOURCES)

    def test_all_entries_have_url_and_lang(self) -> None:
        for entry in ALL_SOURCES:
            assert entry.url.startswith("http")
            assert entry.lang in ("ja", "en")


class TestCrawlerUtils:
    def test_clean_text_removes_script(self) -> None:
        from bs4 import BeautifulSoup
        html = "<html><body><script>alert(1)</script><main><p>Hello DynamoDB</p></main></body></html>"
        soup = BeautifulSoup(html, "lxml")
        result = _clean_text(soup)
        assert "alert" not in result
        assert "Hello DynamoDB" in result

    def test_extract_keywords_from_meta(self) -> None:
        from bs4 import BeautifulSoup
        html = '<html><head><meta name="keywords" content="DynamoDB, GSI, partition key"></head><body></body></html>'
        soup = BeautifulSoup(html, "lxml")
        keywords = _extract_keywords(soup)
        assert "DynamoDB" in keywords

    def test_extract_section_from_h1(self) -> None:
        from bs4 import BeautifulSoup
        html = "<html><body><h1>Global Secondary Indexes</h1></body></html>"
        soup = BeautifulSoup(html, "lxml")
        section = _extract_section(soup)
        assert "Global Secondary Indexes" in section


class TestChunker:
    def _make_page(self, content: str) -> CrawledPage:
        return CrawledPage(
            url="https://example.com/test",
            lang="ja",
            source_type="developer_guide",
            title="Test Page",
            section="Test Section",
            content=content,
            keywords=["DynamoDB"],
        )

    def test_chunk_single_short_page(self) -> None:
        page = self._make_page("DynamoDB はフルマネージド NoSQL データベースサービスです。" * 5)
        chunks = chunk_pages([page])
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_chunk_preserves_metadata(self) -> None:
        page = self._make_page("テスト " * 100)
        chunks = chunk_pages([page])
        for chunk in chunks:
            assert chunk.url == page.url
            assert chunk.lang == page.lang
            assert chunk.title == page.title

    def test_chunk_index_is_sequential(self) -> None:
        page = self._make_page("テスト " * 1000)
        chunks = chunk_pages([page])
        for expected_idx, chunk in enumerate(chunks):
            assert chunk.chunk_index == expected_idx

    def test_chunk_long_content_splits(self) -> None:
        long_content = "DynamoDB partition key design considerations. " * 200
        page = self._make_page(long_content)
        chunks = chunk_pages([page])
        assert len(chunks) > 1
