// ==UserScript==
// @name         get-aws-document-linkTitlePosition
// @namespace    https://github.com/suguruoo/suguruoo-labs
// @version      2.2.0-diag
// @description  AWS ドキュメントの H1/H2/H3 見出し下にコピーボタンを追加
// @author       suguruoo
// @match        https://docs.aws.amazon.com/*
// @grant        none
// @run-at       document-end
// ==/UserScript==

(function () {
  'use strict';

  const WRAPPER_FOR_ATTR = 'data-awscopy-for';

  // -------------------------------------------------------------------
  // イベント委任: document レベルでクリックを捕捉する
  // ボタンレベルの addEventListener が届かない場合の代替手段
  // -------------------------------------------------------------------
  document.addEventListener('click', function (e) {
    var btn = e.target;
    // クリックされた要素またはその親がボタンかどうか確認
    while (btn && btn.tagName !== 'BUTTON') { btn = btn.parentElement; }
    if (!btn || !btn.hasAttribute('data-awscopy-btn')) return;

    // クリックが届いた確認 → すぐに表示変化
    btn.textContent = '⏳ CLICKED (document delegation)';
    btn.style.color = 'red';
    btn.style.borderColor = 'red';

    var headingId = btn.getAttribute('data-awscopy-btn');
    var headingTag = btn.getAttribute('data-awscopy-tag');
    var heading = headingId ? document.getElementById(headingId) : null;
    if (!heading) return;

    var title = heading.textContent.trim();
    var base = window.location.href.split('#')[0];
    var anchor = headingTag !== 'H1' ? '#' + headingId : '';
    var text = '[] ' + title + '\n' + base + anchor;

    // クリップボードにコピー
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        btn.textContent = '✅ successed!!';
        btn.style.color = '#1d8348';
        btn.style.borderColor = '#1d8348';
        setTimeout(function () {
          btn.textContent = '🏷️ Copy this section to the clipboard';
          btn.style.color = '#0972d3';
          btn.style.borderColor = '#0972d3';
        }, 2000);
      }).catch(function (err) {
        btn.textContent = '❌ clipboard error: ' + err.message;
        setTimeout(function () { btn.textContent = '🏷️ Copy this section to the clipboard'; }, 3000);
      });
    } else {
      // execCommand フォールバック
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;pointer-events:none;';
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      try { document.execCommand('copy'); } catch(e) {}
      document.body.removeChild(ta);
      btn.textContent = '✅ successed!! (execCommand)';
      btn.style.color = '#1d8348';
      setTimeout(function () {
        btn.textContent = '🏷️ Copy this section to the clipboard';
        btn.style.color = '#0972d3';
      }, 2000);
    }
  }, true); // useCapture=true: バブリング前のキャプチャフェーズで捕捉

  // -------------------------------------------------------------------
  // ボタン生成
  // -------------------------------------------------------------------
  function createButton(headingId, headingTag) {
    var btn = document.createElement('button');
    btn.textContent = '🏷️ Copy this section to the clipboard';
    btn.setAttribute('type', 'button');
    // data 属性に heading 情報を保存 (イベント委任ハンドラから参照する)
    btn.setAttribute('data-awscopy-btn', headingId);
    btn.setAttribute('data-awscopy-tag', headingTag);
    btn.style.cssText = [
      'display:inline-flex', 'align-items:center',
      'padding:6px 14px', 'margin:6px 0 10px',
      'font-size:12px', 'font-weight:700', 'line-height:1.4',
      'color:#0972d3', 'background:transparent',
      'border:1px solid #0972d3', 'border-radius:8px',
      'cursor:pointer', 'font-family:inherit', 'white-space:nowrap',
      'transition:background 0.15s,color 0.15s',
      'pointer-events:auto',   // 親要素の none を上書き
      'position:relative',
      'z-index:9999',
    ].join(';');
    return btn;
  }

  // -------------------------------------------------------------------
  // wrapper 挿入位置決定
  // -------------------------------------------------------------------
  function insertWrapper(heading, wrapper) {
    if (heading.tagName === 'H1') {
      var ref = heading.nextElementSibling;
      while (ref && ref.tagName.toLowerCase() !== 'p') { ref = ref.nextElementSibling; }
      if (ref) { heading.parentNode.insertBefore(wrapper, ref); }
      else      { heading.insertAdjacentElement('afterend', wrapper); }
    } else {
      heading.insertAdjacentElement('afterend', wrapper);
    }
  }

  // -------------------------------------------------------------------
  // ボタン挿入
  // -------------------------------------------------------------------
  function injectButtons() {
    var container = document.querySelector('#main-col-body') || document.body;
    var headings = container.querySelectorAll('h1[id],h2[id],h3[id]');
    headings.forEach(function (heading) {
      if (!heading.isConnected || !heading.parentNode) return;
      if (document.querySelector('[' + WRAPPER_FOR_ATTR + '="' + heading.id + '"]')) return;
      var wrapper = document.createElement('div');
      wrapper.setAttribute(WRAPPER_FOR_ATTR, heading.id);
      wrapper.style.cssText = 'display:block;pointer-events:auto;position:relative;z-index:9999;';
      wrapper.appendChild(createButton(heading.id, heading.tagName));
      insertWrapper(heading, wrapper);
    });
  }

  // MutationObserver
  var reinjecting = false;
  var observer = new MutationObserver(function (mutations) {
    if (reinjecting) return;
    for (var i = 0; i < mutations.length; i++) {
      var removed = mutations[i].removedNodes;
      for (var j = 0; j < removed.length; j++) {
        var node = removed[j];
        if (node.nodeType !== 1) continue;
        var wasOurs = node.hasAttribute(WRAPPER_FOR_ATTR) ||
          (node.querySelector && node.querySelector('[' + WRAPPER_FOR_ATTR + ']'));
        if (wasOurs) {
          reinjecting = true;
          setTimeout(function () { try { injectButtons(); } finally { reinjecting = false; } }, 200);
          return;
        }
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });

  // SPA
  var lastUrl = location.href;
  function onUrlChange() {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      setTimeout(injectButtons, 500);
      setTimeout(injectButtons, 1500);
    }
  }
  window.addEventListener('popstate', onUrlChange);
  var _push    = history.pushState.bind(history);
  var _replace = history.replaceState.bind(history);
  history.pushState    = function () { _push.apply(history, arguments);    onUrlChange(); };
  history.replaceState = function () { _replace.apply(history, arguments); onUrlChange(); };

  injectButtons();
  window.addEventListener('load', function () {
    setTimeout(injectButtons, 300);
    setTimeout(injectButtons, 800);
  });
})();
