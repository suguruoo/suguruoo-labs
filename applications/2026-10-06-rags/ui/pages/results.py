# ui/pages/results.py
"""結果確認ページ (/results)。

実行済みの RAG セッションを JSON から読み込み、
タイミング・ヒット数のランキング付きカードで比較表示する。
"""

from __future__ import annotations

import os
import sys

import requests
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_API_URL = os.environ.get("API_URL", "http://localhost:8000")

_SOURCE_CONFIG = {
    "postgres": {"label": "🟠 PostgreSQL", "color": "#1e40af"},
    "mysql":    {"label": "🟡 MySQL",      "color": "#166534"},
    "qdrant":   {"label": "🟢 Qdrant",     "color": "#6b21a8"},
    "web":      {"label": "🌐 WebFetch",   "color": "#92400e"},
}

_RANK_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _dense_rank(values: list[float], lower_is_better: bool = False) -> list[int]:
    """Dense rank（同値同順位、1,2,2,4 方式）を計算する。"""
    sorted_unique = sorted(set(values), reverse=not lower_is_better)
    rank_map = {v: i + 1 for i, v in enumerate(sorted_unique)}
    return [rank_map[v] for v in values]


def _rank_badge(rank: int) -> str:
    return _RANK_MEDALS.get(rank, "😢")


def _render_summary_card(
    src: str,
    result: dict,
    timing_ranks: dict,
    hit_ranks: dict,
    in_token_ranks: dict,
    out_token_ranks: dict,
) -> None:
    """1ソースのサマリーカードを描画する。"""
    cfg = _SOURCE_CONFIG.get(src, {"label": src, "color": "#333"})
    retry    = result.get("retry_count", 0)
    total_sec = result.get("total_sec", 0.0)
    hit_count = result.get("hit_count", 0)
    in_tok   = result.get("total_input_tokens", 0)
    out_tok  = result.get("total_output_tokens", 0)
    tr  = timing_ranks.get(src, 0)
    hr  = hit_ranks.get(src, 0)
    ir  = in_token_ranks.get(src, 0)
    orr = out_token_ranks.get(src, 0)
    retry_txt = f"（再検索 {retry} 回）" if retry > 0 else ""

    st.markdown(f"""
<div style="border:1px solid {cfg['color']};border-radius:8px;
            padding:10px 14px;margin-bottom:6px;">
  <div style="font-weight:700;font-size:1rem;color:{cfg['color']};">
    {cfg['label']}
  </div>
  <div style="font-size:0.82rem;margin-top:4px;">✅ 完了{retry_txt}</div>
  <div style="display:flex;gap:12px;margin-top:8px;font-size:0.82rem;flex-wrap:wrap;">
    <div><b>⏱ TotalTime</b><br>{total_sec:.2f}s &nbsp;{_rank_badge(tr)}</div>
    <div><b>📄 Hit Docs</b><br>{hit_count} 件 &nbsp;{_rank_badge(hr)}</div>
    <div><b>🔄 Retry</b><br>{retry} 回</div>
    <div><b>📥 Input Tokens</b><br>{in_tok:,} &nbsp;{_rank_badge(ir)}</div>
    <div><b>📤 Output Tokens</b><br>{out_tok:,} &nbsp;{_rank_badge(orr)}</div>
  </div>
</div>
""", unsafe_allow_html=True)


def _render_timing_breakdown(result: dict) -> None:
    """タイミング内訳テーブルを描画する。"""
    qa  = result.get("query_analyze_sec", 0.0)
    rt  = result.get("retrieve_sec", 0.0)
    ev  = result.get("evaluate_sec", 0.0)
    gen = result.get("generate_sec", 0.0)
    tot = result.get("total_sec", 0.0)
    st.markdown(f"""
| ステップ | 時間 |
|---|---:|
| ① Query Analyze | `{qa:.2f}s` |
| ② Retrieve | `{rt:.2f}s` |
| ③ Evaluate | `{ev:.2f}s` |
| ⑤ Generate | `{gen:.2f}s` |
| **Total** | **`{tot:.2f}s`** |
""")


def _render_detail_page(data: dict, result_id: str) -> None:
    """1件の実行結果の詳細ページを描画する。"""
    params  = data.get("params", {})
    results = data.get("results", {})
    ts      = data.get("timestamp", "")

    st.markdown(f"## 🔍 実行結果詳細")
    st.caption(f"ID: `{data.get('id','')}` | 実行日時: {ts[:19].replace('T',' ')}")

    st.markdown("### ❓ 質問")
    st.info(params.get("question", ""))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Model",     params.get("model", ""))
    c2.metric("Top-K",     str(params.get("top_k", "")))
    c3.metric("Language",  params.get("language", ""))
    c4.metric("Max Retry", str(params.get("max_retry", "")))

    st.divider()

    sources = [s for s in ["postgres", "mysql", "qdrant", "web"] if s in results]

    # ── ランキング計算（Dense rank, lower_is_better でトークンも少ない方が上位）──
    total_secs   = [results[s].get("total_sec",           9999.0) for s in sources]
    hit_counts   = [results[s].get("hit_count",           0)      for s in sources]
    in_tokens    = [results[s].get("total_input_tokens",  999999) for s in sources]
    out_tokens   = [results[s].get("total_output_tokens", 999999) for s in sources]

    time_ranks_l    = _dense_rank(total_secs,  lower_is_better=True)
    hit_ranks_l     = _dense_rank(hit_counts,  lower_is_better=False)
    in_token_ranks_l  = _dense_rank(in_tokens,  lower_is_better=True)
    out_token_ranks_l = _dense_rank(out_tokens, lower_is_better=True)

    timing_ranks    = {s: time_ranks_l[i]      for i, s in enumerate(sources)}
    hit_ranks       = {s: hit_ranks_l[i]       for i, s in enumerate(sources)}
    in_token_ranks  = {s: in_token_ranks_l[i]  for i, s in enumerate(sources)}
    out_token_ranks = {s: out_token_ranks_l[i] for i, s in enumerate(sources)}

    # ── サマリーカード（コメント付き）──
    st.markdown("### 📊 サマリー比較")
    comments = data.get("comments", {})
    card_cols = st.columns(len(sources))
    for col, src in zip(card_cols, sources):
        with col:
            _render_summary_card(
                src, results[src],
                timing_ranks, hit_ranks,
                in_token_ranks, out_token_ranks,
            )
            # ── コメント入力エリア ──
            existing = comments.get(src, "")
            new_comment = st.text_area(
                label="💬 Comment",
                value=existing,
                height=80,
                key=f"comment_{result_id}_{src}",
                placeholder="メモを入力...",
                label_visibility="collapsed",
            )
            if st.button("更新", key=f"save_{result_id}_{src}", use_container_width=True):
                try:
                    r = requests.patch(
                        f"{_API_URL}/results/{result_id}/comment",
                        json={"source": src, "comment": new_comment},
                        timeout=5,
                    )
                    if r.ok:
                        st.success("保存しました", icon="✅")
                    else:
                        st.error(f"保存失敗: {r.status_code}")
                except Exception as exc:
                    st.error(f"API エラー: {exc}")

    st.divider()

    # ── 各ソース詳細（最終回答 / タイミング / Docs） ──
    st.markdown("### 💬 各ソース詳細")
    for src in sources:
        r   = results[src]
        cfg = _SOURCE_CONFIG.get(src, {"label": src, "color": "#333"})
        tr  = timing_ranks[src]
        hr  = hit_ranks[src]

        with st.expander(
            f"{cfg['label']}  "
            f"⏱ {_rank_badge(tr)} `{r.get('total_sec',0):.2f}s`  "
            f"📄 {_rank_badge(hr)} `{r.get('hit_count',0)}件`",
            expanded=True,
        ):
            tab_ans, tab_time, tab_docs = st.tabs(["💬 最終回答", "⏱ タイミング内訳", "📄 Hit Docs"])
            with tab_ans:
                ans = r.get("final_answer", "")
                if ans.startswith("エラーが発生しました"):
                    st.error(ans)
                else:
                    st.markdown(ans)
            with tab_time:
                _render_timing_breakdown(r)
            with tab_docs:
                top_docs = r.get("top_docs", [])
                if not top_docs:
                    st.info("取得文書なし")
                for doc in top_docs:
                    st.markdown(
                        f"**[{doc.get('rank','')}]** `score={doc.get('score',0):.4f}` "
                        f"— {doc.get('title','')[:60]}"
                    )
                    if doc.get("url"):
                        st.caption(doc["url"])


# ── ページエントリーポイント ───────────────────────────────────────
st.set_page_config(
    page_title="Results — DynamoDB RAG PoC",
    page_icon="📊",
    layout="wide",
)
st.markdown("# 📊 実行結果")

try:
    resp = requests.get(f"{_API_URL}/results", timeout=5)
    result_list = resp.json() if resp.ok else []
except Exception:
    result_list = []

if not result_list:
    st.info("まだ実行結果がありません。`/` ページで質問を送信してください。")
    st.stop()

options = {
    f"{r['timestamp'][:19].replace('T',' ')} — {r['question'][:45]}": r["id"]
    for r in result_list
}
selected_label = st.selectbox("実行履歴を選択", list(options.keys()))
if not selected_label:
    st.stop()
selected_id = options[selected_label]

try:
    detail_resp = requests.get(f"{_API_URL}/results/{selected_id}", timeout=5)
    if detail_resp.ok:
        _render_detail_page(detail_resp.json(), selected_id)
    else:
        st.error("結果の取得に失敗しました")
except Exception as exc:
    st.error(f"API 接続エラー: {exc}")

