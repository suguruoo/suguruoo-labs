# ui/components/settings_panel.py
"""左パネル：RAG パラメータ設定コンポーネント。"""

from __future__ import annotations

import streamlit as st


def render_settings_panel() -> dict:
    """設定パネルを描画してパラメータ辞書を返す。

    Returns:
        RAG パラメータの辞書。
    """
    st.markdown(
        "<div style='font-size:1.05rem; font-weight:700; letter-spacing:0.05em;"
        " color:#93c5fd; margin-bottom:4px;'>⚙️ 設定</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<hr style='border:none; border-top:1px solid #3d4f6e; margin:4px 0 12px 0;'>",
        unsafe_allow_html=True,
    )

    model = st.selectbox(
        "🤖 Model",
        options=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        index=0,
        help="使用する LLM モデル",
    )

    st.markdown(
        "<div style='font-size:0.7rem; color:#64748b; margin:8px 0 2px 0;'>── Retrieval ──</div>",
        unsafe_allow_html=True,
    )

    top_k = st.slider(
        "🔢 Top-K",
        min_value=1,
        max_value=20,
        value=5,
        step=1,
        help="検索で取得する上位文書数",
    )

    max_retry = st.slider(
        "🔄 Max Retry",
        min_value=1,
        max_value=5,
        value=3,
        step=1,
        help="十分性評価が不十分な場合の最大再検索回数",
    )

    st.markdown(
        "<div style='font-size:0.7rem; color:#64748b; margin:8px 0 2px 0;'>── Generation ──</div>",
        unsafe_allow_html=True,
    )

    top_p = st.slider(
        "🎯 Top-P",
        min_value=0.0,
        max_value=1.0,
        value=0.9,
        step=0.05,
        help="Nucleus Sampling の確率閾値",
    )

    temperature = st.slider(
        "🌡️ Temperature",
        min_value=0.0,
        max_value=2.0,
        value=0.3,
        step=0.1,
        help="生成の多様性（低いほど決定的）",
    )

    reasoning = st.toggle(
        "🧠 Reasoning",
        value=True,
        help="推論ステップの詳細表示",
    )

    st.markdown(
        "<div style='font-size:0.7rem; color:#64748b; margin:8px 0 2px 0;'>── Embedding ──</div>",
        unsafe_allow_html=True,
    )

    embedding_model = st.selectbox(
        "📐 Embed Model",
        options=["text-embedding-3-small", "text-embedding-3-large"],
        index=0,
        help="使用する埋め込みモデル",
    )

    language = st.selectbox(
        "🌐 Language",
        options=["ja+en", "ja", "en"],
        index=0,
        help="検索対象の言語",
    )

    return {
        "model": model,
        "top_k": top_k,
        "top_p": top_p,
        "temperature": temperature,
        "reasoning": reasoning,
        "embedding_model": embedding_model,
        "language": language,
        "max_retry": max_retry,
    }

