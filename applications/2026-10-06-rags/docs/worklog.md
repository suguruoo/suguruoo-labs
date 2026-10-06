# 🗂️ RAG PoC Work Log

> DynamoDB RAG PoC における RAG 精度・実装上の課題と解決策の記録。
> このファイルは `/worklog` ページから直接編集・保存できます。

---

## 1. 設計：パイプライン構成の見直し

### 課題
当初、LangChain の分岐→合流型1本チェーンで4ソースを処理しようとした。共通 QueryAnalyzer / 共通 Evaluator / 共通 Ranker では「4ソース統合の回答」しか得られず、DBごとの精度比較が不能だった。

### 解決策（ADR-001）
**4本完全独立パイプライン**を採用。`asyncio.create_task` で並列起動し合流なし。各パイプラインが独立した最終回答を持つ。

### 残課題
- 4本並列は LLM コストが最大4倍。本番化時はコスト最適化が必要

---

## 2. Embedding：OpenAI API 依存の排除

### 課題
データ収集フェーズで `text-embedding-3-small`（OpenAI API）を使用していたが、**API クレジットが枯渇**してデータ収集が途中停止。DBはセルフホストなのに embedding 生成だけが外部 API に依存していた矛盾。

### 解決策（ADR-005）
`intfloat/multilingual-e5-large`（sentence-transformers）にローカル切り替え。

- embedding 次元が 1536 → 1024 に変わるため DB スキーマ再作成が必要だった
- **e5 モデルは `passage:` / `query:` プレフィックスが必須** → 格納時と検索時で使い分けないと精度が著しく下がる

### 精度上の注意点
- 「クォーター」（カタカナ）で検索しても「quota」（英語）ドキュメントに近い embedding が生成されないケースがある → tsvector との RRF で補完が必要

---

## 3. PostgreSQL：Hybrid Search 導入

### 課題
「DynamoDB のグローバル index のクォーターは？」に対して **Limits.html が Top5 に入らない**問題。3層の原因が重なっていた：

1. **QueryAnalyzer が lang_filter を "en" に自己判断** → JA チャンクが全除外
2. **embedding スコア分布** → GSI.html が高スコアを占有（数値表の Limits.html は意味密度が低い）
3. **同一 URL の複数チャンクが RRF スコアを重複加算**

### 解決策
- `lang_filter = params.language`（LLM 判断廃止）
- `candidate_size = top_k × 4`（候補プール拡大）
- **Hybrid RRF**：embedding rank + tsvector rank を統合 + `DISTINCT ON (url)` で URL 単位 dedup
- **ASCII 抽出**：「DynamoDB クォーター GSI 制限」→「DynamoDB GSI」で tsvector にヒット

### 残課題
- tsvector は `simple` 辞書のため `quota`/`quotas` が別トークン。`english` 辞書への切り替えで改善可能
- QueryAnalyzer の英語キーワード出力が LLM によって不安定。Few-shot examples の追加が有効

---

## 4. MySQL：文字化けと検索精度

### 課題（2段階で発覚）

**フェーズ1：文字化け**
- `pymysql.connect(charset="utf8mb4")` だけでは `character_set_client` がサーバーデフォルト（latin1）のまま
- 日本語 1,990 件が文字化けして格納 → ほぼ検索不能な状態

**フェーズ2：検索精度**
- ngram が `+グローバルインデックス` を「グロ」「ロー」「ーバ」と2文字分割 → スコア分散
- 同一 URL の複数チャンクが重複ヒット

### 解決策
```python
conn.autocommit(True)
cur.execute("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci")
cur.execute("SET CHARACTER SET utf8mb4")
conn.autocommit(False)
```
- **ASCII 抽出**で英語キーワードのみ BOOLEAN クエリに渡す
- **URL dedup**（`ROW_NUMBER() OVER (PARTITION BY url)`）
- **NATURAL LANGUAGE MODE fallback**（BOOLEAN ヒット 0 件時）

### 注意点
- `SET NAMES` のみでは autocommit のトランザクション境界で latin1 に戻ることがある → `SET CHARACTER SET utf8mb4` の併用が必要
- 日本語クエリで文字化けデータが返る場合、データ再投入が必要（DROP → init_schema → load_chunks）

---

## 5. Qdrant：API バージョン変更

### 課題
`qdrant-client` v1.11+ で `client.search()` が廃止され実行時エラー。

### 解決策
```python
# Before（廃止）
results = client.search(query_vector=embedding, ...)
# After
results = client.query_points(query=embedding, ...).points
```

### 注意点
- `qdrant-client` はバージョンアップ時に破壊的変更が多い → `pyproject.toml` でバージョン固定推奨
- `vectors_count` も廃止 → `points_count` を使う

---

## 6. QueryAnalyzer：lang_filter 誤設定

### 課題
プロンプトに `lang_filter` の出力を指示していたため、**LLM が `language=ja+en` 設定を無視して `"en"` のみを返すことがあった**。JA の全チャンク（1,990件）が検索除外されていた。

### 解決策
プロンプトから `lang_filter` 出力指示を削除し、`lang_filter = params.language` でユーザー設定を直接使用。

### 教訓
- **LLM に「システム設定値を判断・出力させる」のは危険** → 設定は必ずコードで直接参照する
- QueryAnalyzer の役割は「検索クエリ形式の生成」であり「システム設定の判断」ではない

---

## 7. トークン集計：Callback 方式の不備

### 課題
`StepLogger`（`AsyncCallbackHandler`）の `on_llm_end` でトークンを集計しようとしたが、常に 0。LLM インスタンスに `callbacks=` を渡していなかったため `on_llm_end` が一切呼ばれていなかった。

### 解決策
Callback 依存を廃止し、`ainvoke` 戻り値の `AIMessage.usage_metadata` から直接参照。

```python
usage = getattr(response, "usage_metadata", None) or {}
step_logger.add_tokens(
    input_tokens=usage.get("input_tokens", 0),
    output_tokens=usage.get("output_tokens", 0),
)
```

### 教訓
- LangChain の Callback は LLM インスタンスに明示的に渡す必要がある（グローバル動作しない）
- `usage_metadata` は LangChain v0.3+ で安定取得可能。Callback より確実

---

## 8. 未解決・継続課題

### 🔴 高優先度

| 課題 | 詳細 | 改善案 |
|---|---|---|
| MySQL 日本語データ確認 | 文字化け修正後のデータが正しいか未検証 | `scripts/check_progress.py` 後、日本語クエリで目視確認 |
| Qdrant 日本語精度 | 日本語クエリで JA 版 Limits.html がヒットするか不明 | 「DynamoDB のクォーター」クエリで検証 |

### 🟡 中優先度

| 課題 | 詳細 | 改善案 |
|---|---|---|
| tsvector 辞書 | `simple` 辞書で語幹解析なし。`quota`/`quotas` 別トークン | `english` 辞書の導入を検討 |
| Evaluator 判定精度 | 「十分」判定が甘く再検索が走らないケースがある | プロンプトに具体的な判定基準（数値の有無等）を追加 |
| data_modeling チャンク少 | 9チャンクのみ。prescriptive-guidance が1HTML集約 | Playwright/Selenium 等の動的ページ対応を検討 |
| QueryAnalyzer 出力安定性 | JSON フォーマットから外れることがある | Few-shot examples 追加または `response_format` (Structured Output) を使用 |

### 🟢 低優先度（PoC 後の改善候補）

| 課題 | 詳細 | 改善案 |
|---|---|---|
| embedding モデルの定量比較 | multilingual-e5-large vs OpenAI の比較なし | 共通テストセットで Recall@K を計測 |
| チャンク戦略の最適化 | 512 tokens / 50 overlap 固定値 | 見出しベースのチャンク分割を検討 |
| Re-ranker 導入 | 単純スコアソートのみ | `cross-encoder/ms-marco-MiniLM-L-6-v2` 等を検討 |
| WebFetch 再現性 | 毎回結果が異なる | 結果キャッシュで再現性確保 |

---

*最終更新: 2026-10-07*
*このファイルは `/worklog` ページから直接編集できます。*
