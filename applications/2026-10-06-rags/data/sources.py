# data/sources.py
"""DynamoDB ドキュメント収集対象 URL 定義。

AWS ドキュメントはトップページが JS リダイレクトのため、
代表的な個別ページを直接指定する。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceEntry:
    """収集対象URLのエントリ。"""

    url: str
    lang: str  # "ja" | "en"
    source_type: str  # "developer_guide" | "data_modeling" | "blog" | "faq"
    label: str


# ---- 日本語: Developer Guide 個別ページ（JS リダイレクト回避）----
JA_DEVELOPER_GUIDE_PAGES: list[SourceEntry] = [
    SourceEntry(
        url=f"https://docs.aws.amazon.com/ja_jp/amazondynamodb/latest/developerguide/{page}",
        lang="ja",
        source_type="developer_guide",
        label=f"DynamoDB DG (JA) - {page}",
    )
    for page in [
        "Introduction.html",
        "HowItWorks.html",
        "HowItWorks.CoreComponents.html",
        "HowItWorks.ReadWriteCapacityMode.html",
        "HowItWorks.Partitions.html",
        "HowItWorks.NamingRulesDataTypes.html",
        "HowItWorks.ReadConsistency.html",
        "bp-general-nosql-design.html",
        "bp-partition-key-design.html",
        "bp-sort-keys.html",
        "bp-indexes.html",
        "bp-gsi.html",
        "bp-adjacency-graphs.html",
        "bp-relational-modeling.html",
        "bp-time-series.html",
        "bp-messaging.html",
        "GSI.html",
        "LSI.html",
        "Streams.html",
        "GlobalTables.html",
        "PointInTimeRecovery.html",
        "TTL.html",
        "Transactions.html",
        "DAX.html",
        "WorkingWithItems.html",
        "WorkingWithTables.html",
        "WorkingWithQueries.html",
        "WorkingWithScans.html",
        "SecondaryIndexes.html",
        "Limits.html",
    ]
]

JA_DATA_MODELING_PAGES: list[SourceEntry] = [
    SourceEntry(
        url="https://docs.aws.amazon.com/ja_jp/prescriptive-guidance/latest/dynamodb-data-modeling/welcome.html",
        lang="ja",
        source_type="data_modeling",
        label="DynamoDB Data Modeling Guide (JA)",
    ),
]

JA_OTHER_SOURCES: list[SourceEntry] = [
    SourceEntry(
        url="https://aws.amazon.com/jp/dynamodb/faqs/",
        lang="ja",
        source_type="faq",
        label="DynamoDB FAQ (JA)",
    ),
    SourceEntry(
        url="https://aws.amazon.com/jp/blogs/news/category/database/amazon-dynamodb/",
        lang="ja",
        source_type="blog",
        label="AWS Blog DynamoDB (JA)",
    ),
]

JA_SOURCES: list[SourceEntry] = JA_DEVELOPER_GUIDE_PAGES + JA_DATA_MODELING_PAGES + JA_OTHER_SOURCES

# ---- 英語: Developer Guide 個別ページ ----
EN_DEVELOPER_GUIDE_PAGES: list[SourceEntry] = [
    SourceEntry(
        url=f"https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/{page}",
        lang="en",
        source_type="developer_guide",
        label=f"DynamoDB DG (EN) - {page}",
    )
    for page in [
        "Introduction.html",
        "HowItWorks.html",
        "HowItWorks.CoreComponents.html",
        "HowItWorks.ReadWriteCapacityMode.html",
        "HowItWorks.Partitions.html",
        "bp-general-nosql-design.html",
        "bp-partition-key-design.html",
        "bp-sort-keys.html",
        "bp-indexes.html",
        "bp-gsi.html",
        "GSI.html",
        "LSI.html",
        "Streams.html",
        "GlobalTables.html",
        "Transactions.html",
        "DAX.html",
        "WorkingWithItems.html",
        "WorkingWithQueries.html",
        "WorkingWithScans.html",
        "Limits.html",
    ]
]

EN_OTHER_SOURCES: list[SourceEntry] = [
    SourceEntry(
        url="https://aws.amazon.com/dynamodb/faqs/",
        lang="en",
        source_type="faq",
        label="DynamoDB FAQ (EN)",
    ),
    SourceEntry(
        url="https://aws.amazon.com/blogs/database/category/database/amazon-dynamodb/",
        lang="en",
        source_type="blog",
        label="AWS Database Blog DynamoDB (EN)",
    ),
]

EN_SOURCES: list[SourceEntry] = EN_DEVELOPER_GUIDE_PAGES + EN_OTHER_SOURCES

ALL_SOURCES: list[SourceEntry] = JA_SOURCES + EN_SOURCES

