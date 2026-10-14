# Tampermonkey 開発知見メモ

> 作成日: 2026-10-14  
> 対象スクリプト: `get-aws-document-linkTitlePosition`  
> 開発期間: 2026-10-13～14（v1.0.0 → v2.3.0）

---

## 1. 最重要: `@grant` の値でスクリプトの実行 world が変わる

### 問題

`@grant GM_setClipboard` を指定すると、Tampermonkey v5.5 (Chrome MV3) 環境では  
スクリプトが **ISOLATED_WORLD または USERSCRIPT_WORLD** で実行される。  
このモードでは **ボタンに `addEventListener` で登録したクリックイベントが一切発火しない**。

### 診断方法

Chrome DevTools の Console タブ（Extensionsフィルタ）でどのファイルがログを出しているか確認する。

| ログの出どころ | 実行モード | クリック動作 |
|---|---|---|
| `content.js: env: inject "..." now` | Content Script モード (MAIN_WORLD 寄り) | ✅ 正常 |
| `background.js: run script ... @ URL` | UserScripts API モード | ❌ クリック不発 |

### 解決策

```js
// ❌ これをするとクリックが届かなくなる (v5.5 Chrome MV3)
// @grant  GM_setClipboard

// ✅ @grant none にする → MAIN_WORLD で実行 → DOM イベント正常
// @grant  none
```

---

## 2. クリップボード API の選択

`@grant none` 環境では `GM_setClipboard` は使えない。代わりに:

```js
async function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    // モダンブラウザ (HTTPS 必須)
    await navigator.clipboard.writeText(text);
    return;
  }
  // フォールバック: execCommand
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;pointer-events:none;';
  document.body.appendChild(ta);
  ta.focus(); ta.select();
  try { document.execCommand('copy'); } catch(e) {}
  document.body.removeChild(ta);
}
```

`GM_setClipboard` を使う場合は必ず callback 付きで呼ぶ（省略すると成否不明）:

```js
// ❌ 戻り値なし。成否がわからない
GM_setClipboard(text, 'text');

// ✅ callback で確認する
GM_setClipboard(text, 'text', function(ok) {
  if (ok !== false) { /* 成功 */ }
});
```

---

## 3. クリックイベントが届かない場合の回避策: イベント委任

ボタン個別の `addEventListener` が world 分離や CSS の
`pointer-events: none` により届かない場合、
**`document` レベルでキャプチャフェーズ委任**すると確実に拾える:

```js
// ❌ world 分離があると届かない
btn.addEventListener('click', function() { ... });

// ✅ document レベルでキャプチャ → world に依らず確実
document.addEventListener('click', function(e) {
  var btn = e.target;
  while (btn && btn.tagName !== 'BUTTON') { btn = btn.parentElement; }
  if (!btn || !btn.hasAttribute('data-my-btn')) return;
  // 処理...
}, true); // ← useCapture=true が重要
```

ボタン側には `data` 属性で必要情報を持たせ、クリックハンドラから参照する:

```js
btn.setAttribute('data-my-btn', headingId);
btn.setAttribute('data-my-tag', headingTag);
```

---

## 4. AWS docs 特有の DOM 構造のはまりどころ

### H1 直後に Angular コンポーネントが挑まる

```html
<h1 id="...">ページタイトル</h1>
<awsdocs-page-header-container>...</awsdocs-page-header-container>
<p>本文...</p>
```

`h1.nextElementSibling` が `<awsdocs-page-header-container>` になるため、
`<p>` の前に到達するまでスキップしながら挿入位置を探す必要がある:

```js
function insertWrapper(heading, wrapper) {
  if (heading.tagName === 'H1') {
    var ref = heading.nextElementSibling;
    while (ref && ref.tagName.toLowerCase() !== 'p') {
      ref = ref.nextElementSibling;
    }
    if (ref) { heading.parentNode.insertBefore(wrapper, ref); }
    else      { heading.insertAdjacentElement('afterend', wrapper); }
  } else {
    heading.insertAdjacentElement('afterend', wrapper);
  }
}
```

### H1 の `id` が空文字になるページがある

`document.getElementById('')` は `null` を返すため、H1 だけ id に依存しない取得方法を使う:

```js
if (headingTag === 'H1') {
  // ❌ getElementById('') → null → 処理終了
  // var heading = document.getElementById(headingId);

  // ✅ querySelector で直接取得
  var h1el = document.querySelector('h1');
  var pageTitle = (h1el ? h1el.textContent.trim() : '') || document.title || '';
}
```

### `#main-col-body` 外に無関係な heading が大量ある

`document.querySelectorAll('h1,h2,h3')` だと Cookie 同意バナー・フッター・サイドバーの
heading にもボタンが挿入される。必ず `#main-col-body` に絞る:

```js
var container = document.querySelector('#main-col-body') || document.body;
container.querySelectorAll('h1[id],h2[id],h3[id]').forEach(...);
// [id] を付けることで id なし heading（TOC等）も自動除外
```

### Angular が DOM を再レンダリングしてボタンを消す

Angular のブートストラップ時に DOM が再構築され、挿入済みの wrapper が削除される。
`MutationObserver` で削除を検知して自動再挿入する:

```js
var observer = new MutationObserver(function(mutations) {
  for (var i = 0; i < mutations.length; i++) {
    var removed = mutations[i].removedNodes;
    for (var j = 0; j < removed.length; j++) {
      var node = removed[j];
      if (node.nodeType !== 1) continue;
      var wasOurs = node.hasAttribute('data-awscopy-for') ||
        (node.querySelector && node.querySelector('[data-awscopy-for]'));
      if (wasOurs) {
        setTimeout(injectButtons, 200);
        return;
      }
    }
  }
});
observer.observe(document.body, { childList: true, subtree: true });
```

### AWS の CSS が `pointer-events: none` を親要素に設定している

wrapper とボタン両方に明示的に上書きする:

```js
wrapper.style.cssText = 'display:block; pointer-events:auto; position:relative; z-index:9999;';
btn.style.pointerEvents = 'auto';
btn.style.position = 'relative';
btn.style.zIndex = '9999';
```

---

## 5. Tampermonkey v5.5+ (Chrome MV3) の設定と挙動

### 「Allow UserScripts」トグル (Chrome 138+)

`chrome://extensions` → Tampermonkey → 「Allow User Scripts」トグルを ON にする必要がある。  
Developer Mode だけでは不十分な場合がある (Chrome バージョンによる)。

### Content Script API 設定

Tampermonkey ダッシュボード → 設定 → Config Mode を **Advanced** に変更すると  
**「Content Script API」** 設定項目が現れる。

| 設定値 | ログ出どころ | 動作 |
|---|---|---|
| `Content Script`（**推奨**） | `content.js` | MAIN_WORLD 寄り。クリックイベント正常 |
| `UserScripts API` | `background.js` | world 分離あり。クリック不発の可能性 |
| `UserScripts API Dynamic` | `background.js` | document-start サポートあり。同様のリスク |

クリックイベント系で問題が起きたら、まずこの設定を `Content Script` に変更して試す。

---

## 6. デバッグ手法

### クリックが届いているか確認する最小テスト

クリップボードや DOM 操作より先に**テキスト変化だけ**をテストする。  
これが変化しない = クリック自体が届いていない:

```js
document.addEventListener('click', function(e) {
  var btn = e.target;
  while (btn && btn.tagName !== 'BUTTON') { btn = btn.parentElement; }
  if (!btn || !btn.hasAttribute('data-my-btn')) return;
  // ← これが変わらないならクリックが届いていない
  btn.textContent = 'CLICKED';
  btn.style.color = 'red';
}, true);
```

### Console から `GM_setClipboard` を呼んでも意味がない

`GM_setClipboard` はスクリプトの isolated world に存在する関数。  
ページの Console (= MAIN_WORLD) から呼ぶと `ReferenceError: GM_setClipboard is not defined`。  
これは正常動作であり、「スクリプト内で動かない」の証拠にならない。

### Console フィルタで Tampermonkey のログだけ見る

Chrome DevTools → Console → filter 欄に `content.js` または `background.js` と入力。  
どの実行経路を通っているか一目でわかる。

---

## 7. 二重挿入防止パターン

heading ごとに一意なキー（`heading.id`）を `data` 属性として wrapper に持たせ、  
既に存在するならスキップする:

```js
var WRAPPER_FOR_ATTR = 'data-awscopy-for';

function injectButtons() {
  container.querySelectorAll('h1[id],h2[id],h3[id]').forEach(function(heading) {
    if (document.querySelector('[' + WRAPPER_FOR_ATTR + '="' + heading.id + '"]')) return;
    var wrapper = document.createElement('div');
    wrapper.setAttribute(WRAPPER_FOR_ATTR, heading.id);
    // ...
  });
}
```

---

## 8. SPA (ページ遷移) 対応

AWS docs は Angular ベースの SPA。`popstate` だけでは検知できない遷移があるため  
`history.pushState` / `replaceState` をラップして URL 変化を検知する:

```js
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
history.pushState    = function() { _push.apply(history, arguments);    onUrlChange(); };
history.replaceState = function() { _replace.apply(history, arguments); onUrlChange(); };
```

---

## 9. バージョン変遷と学習曲線まとめ

| バージョン | 主な変更 | 結果 |
|---|---|---|
| v1.0〜1.5 | `@grant none` + `navigator.clipboard` | ✅ 動作 |
| v1.6.0 | `@grant GM_setClipboard` に変更 | ❌ クリック不発（原因不明のまま継続） |
| v1.6.1〜1.10 | `#main-col-body` 絞り込み等の改善 | ❌ クリック不発は未解決 |
| v2.2.0 | `@grant none` 復帰 + document 委任 | ✅ **クリック動作** |
| v2.3.0 | H1 コピー失敗修正 + パンくず復元 | ✅ 全機能動作 |

**教訓: `@grant none` + `navigator.clipboard` + document レベルイベント委任**が  
Tampermonkey v5.5+ Chrome MV3 環境での最も安定した組み合わせ。
