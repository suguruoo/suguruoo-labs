# ui/pages/worklog.py
"""Work Log ページ (/worklog)。

docs/worklog.md を読み込んでマークダウン表示する。
編集モードに切り替えるとテキストエディタが開き、
保存するとプロジェクト内の worklog.md ファイルに直接書き込む。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_WORKLOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "worklog.md"
)


def _load() -> str:
    """worklog.md を読み込む。存在しない場合は空文字を返す。"""
    if not os.path.exists(_WORKLOG_PATH):
        return "# Work Log\n\nまだ記録がありません。"
    with open(_WORKLOG_PATH, encoding="utf-8") as f:
        return f.read()


def _save(content: str) -> None:
    """worklog.md に書き込む。"""
    os.makedirs(os.path.dirname(_WORKLOG_PATH), exist_ok=True)
    with open(_WORKLOG_PATH, "w", encoding="utf-8") as f:
        f.write(content)


# ── ページ設定 ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Work Log — DynamoDB RAG PoC",
    page_icon="🗂️",
    layout="wide",
)

st.markdown("# 🗂️ Work Log")
st.caption("RAG 精度・実装上の課題と解決策の記録。編集して保存すると `docs/worklog.md` に同期されます。")

# ── 編集 / 表示 モード切り替え ──────────────────────────────────────
col_title, col_toggle = st.columns([6, 1])
with col_toggle:
    edit_mode = st.toggle("✏️ 編集", value=False, key="worklog_edit_mode")

st.divider()

content = _load()

if edit_mode:
    # ── 編集モード ──────────────────────────────────────────────────
    st.caption("📝 Markdown を直接編集できます。保存すると `docs/worklog.md` に書き込まれます。")

    edited = st.text_area(
        label="worklog_editor",
        value=content,
        height=700,
        label_visibility="collapsed",
        key="worklog_textarea",
    )

    save_col, preview_col, _ = st.columns([2, 2, 6])

    with save_col:
        if st.button("💾 保存", type="primary", use_container_width=True):
            # 最終更新日時を末尾に自動更新
            now_str = datetime.now().strftime("%Y-%m-%d")
            lines = edited.rstrip().splitlines()
            # 既存の最終更新行を置き換え or 追記
            if lines and lines[-1].startswith("*最終更新:"):
                lines[-1] = f"*最終更新: {now_str}*"
            else:
                lines.append("")
                lines.append(f"*最終更新: {now_str}*")
            final_content = "\n".join(lines) + "\n"
            _save(final_content)
            st.success(f"保存しました（{now_str}）", icon="✅")
            st.rerun()

    with preview_col:
        show_preview = st.button("👁 プレビュー", use_container_width=True)

    if show_preview:
        st.divider()
        st.markdown("#### プレビュー")
        st.markdown(edited)

else:
    # ── 表示モード ──────────────────────────────────────────────────
    st.markdown(content)
