# ui/app.py
"""Streamlit メインアプリ。

レイアウト:
  ┌─────────────────────────────────────────────────────┐
  │  🔍 DynamoDB RAG PoC                                 │
  │  [──────────── 質問入力 ────────────────] [🚀 送信]  │
  ├──────────┬──────────────────────────────────────────┤
  │ ⚙️ 設定  │ PostgreSQL │ MySQL │ Qdrant │ WebFetch    │
  │  (左     │                                           │
  │   パネル)│  各パイプラインのステップをリアルタイム表示│
  └──────────┴──────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import os
import sys

import requests
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ui.components.settings_panel import render_settings_panel
from ui.components.step_renderer import _STEP_ICONS, render_step

_API_URL = os.environ.get("API_URL", "http://localhost:8000")

_SOURCE_CONFIG = {
    "postgres": {"label": "🟠 PostgreSQL", "subtitle": "Document DB (pgvector)"},
    "mysql":    {"label": "🟡 MySQL",      "subtitle": "RDB Index (FULLTEXT)"},
    "qdrant":   {"label": "🟢 Qdrant",     "subtitle": "Vector DB (cosine)"},
    "web":      {"label": "🌐 WebFetch",   "subtitle": "OpenAI web_search"},
}

_CSS = """
<style>
/* ── 設定パネル（1列目）を背景色 + 右ボーダーで視覚分離 ── */
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child {
    background-color: #1a1f2e;
    border-right: 2px solid #3d4f6e;
    border-radius: 8px 0 0 8px;
    padding: 12px 12px 16px 12px !important;
}
/* 設定パネル内テキスト色 */
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child label,
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child p,
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child span {
    color: #e2e8f0 !important;
}
/* スライダー間の余白を詰める */
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child
    div[data-testid="stSlider"] { margin-bottom: -8px !important; }
/* ソースカラム（2列目以降）の上部アクセントライン */
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:not(:first-child) {
    border-top: 3px solid #3d4f6e;
    padding-top: 10px !important;
}
/* 全体余白 */
.main .block-container { padding-top: 0.6rem; }
/* 送信ボタン高さをテキスト入力に合わせる */
div[data-testid="stButton"] > button[kind="primary"] {
    height: 42px;
    font-size: 1rem;
    font-weight: 600;
    border-radius: 6px;
    width: 100%;
    margin-top: 0 !important;
}
</style>
"""


def _call_api_sse(
    question: str,
    params: dict,
    col_containers: dict[str, object],
) -> None:
    """API に SSE リクエストを送り、各カラムにステップをリアルタイム表示する。

    各カラムに st.container() を確保し、SSE イベントを受け取るたびに
    そのカラムへ逐次書き込む。

    Args:
        question: ユーザーの質問。
        params: RAG パラメータ辞書。
        col_containers: ソース名 → Streamlit カラムのマップ。
    """
    payload = {
        "question": question,
        "model": params.get("model", "gpt-4o"),
        "top_k": params.get("top_k", 5),
        "top_p": params.get("top_p", 0.9),
        "temperature": params.get("temperature", 0.3),
        "reasoning": params.get("reasoning", True),
        "embedding_model": params.get("embedding_model", "text-embedding-3-small"),
        "language": params.get("language", "ja+en"),
        "max_retry": params.get("max_retry", 3),
    }

    # 各カラムに書き込み用コンテナを作成
    step_areas: dict[str, object] = {}
    for src in col_containers:
        with col_containers[src]:
            step_areas[src] = st.container()

    # 各カラムにステータス行とステップ積み込みコンテナを確保
    status_texts: dict[str, object] = {}
    step_containers: dict[str, object] = {}
    for src in _SOURCE_CONFIG:
        with step_areas[src]:
            status_texts[src] = st.empty()
            status_texts[src].info("⏳ 処理中...")
            step_containers[src] = st.container()

    try:
        with requests.post(
            f"{_API_URL}/query",
            json=payload,
            stream=True,
            timeout=300,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()

            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                if not decoded.startswith("data:"):
                    continue
                raw = decoded[len("data:"):].strip()
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("event_type", "")
                source = event.get("source", "")
                data = event.get("data", {})

                if event_type == "step" and source in step_containers:
                    step = data.pop("step", "")
                    attempt = data.pop("attempt", 1)
                    render_step(
                        step=step,
                        data=data,
                        attempt=attempt,
                        container=step_containers[source],
                    )
                    label = _STEP_ICONS.get(step, step)
                    retry_txt = f" (再試行 {attempt})" if attempt > 1 else ""
                    status_texts[source].info(f"⏳ {label}{retry_txt}")

                elif event_type == "result":
                    for src_name, result in data.items():
                        if src_name not in step_areas:
                            continue
                        final_answer = result.get("final_answer", "")
                        retry = result.get("retry_count", 0)
                        is_error = final_answer.startswith("エラーが発生しました")
                        if is_error:
                            status_texts[src_name].error("❌ エラー")
                        else:
                            badge = f"（再検索 {retry} 回）" if retry > 0 else ""
                            status_texts[src_name].success(f"✅ 完了{badge}")
                        with step_areas[src_name]:
                            if is_error:
                                st.error(final_answer)
                            else:
                                st.markdown("---")
                                st.markdown("### 💬 最終回答")
                                st.markdown(final_answer)

                elif event_type == "done":
                    break

                elif event_type == "error":
                    st.error(f"API エラー: {data.get('error', '不明')}")
                    break

    except requests.ConnectionError:
        st.error(
            f"API サーバーに接続できません。`uvicorn api.main:app --reload --port 8000` を起動してください。\n"
            f"URL: {_API_URL}/query"
        )
    except Exception as exc:
        st.error(f"予期しないエラー: {exc}")


def main() -> None:
    """Streamlit アプリのエントリーポイント。"""
    st.set_page_config(
        page_title="DynamoDB RAG PoC",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown("## 🔍 DynamoDB RAG PoC")

    # ── ① 質問バー（フル幅・最上部）──
    q_col, btn_col = st.columns([8, 1])
    with q_col:
        question = st.text_input(
            label="question",
            label_visibility="collapsed",
            placeholder="💬 例: DynamoDB の GSI はどんなときに使うべきですか？",
            key="question_input",
        )
    with btn_col:
        submitted = st.button("🚀 送信", type="primary", use_container_width=True)

    st.divider()

    # ── ② 設定パネル(1列) + 4ソースカラム(4列) ──
    col_settings, col_pg, col_mysql, col_qdrant, col_web = st.columns([1, 2, 2, 2, 2])

    with col_settings:
        rag_params = render_settings_panel()

    col_containers: dict[str, object] = {
        "postgres": col_pg,
        "mysql":    col_mysql,
        "qdrant":   col_qdrant,
        "web":      col_web,
    }

    # 初期ヘッダー（送信前）
    if not submitted:
        for src, cfg in _SOURCE_CONFIG.items():
            with col_containers[src]:
                st.markdown(f"### {cfg['label']}")
                st.caption(cfg["subtitle"])
                st.divider()
                st.info("質問を入力して送信してください")

    # 送信処理
    if submitted:
        if not question.strip():
            st.warning("質問を入力してください。")
        else:
            for src, cfg in _SOURCE_CONFIG.items():
                with col_containers[src]:
                    st.markdown(f"### {cfg['label']}")
                    st.caption(cfg["subtitle"])
                    st.divider()
            _call_api_sse(
                question=question.strip(),
                params=rag_params,
                col_containers=col_containers,
            )


if __name__ == "__main__":
    main()

