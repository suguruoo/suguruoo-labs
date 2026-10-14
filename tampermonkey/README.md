# 🐵 Tampermonkey Scripts

[Tampermonkey](https://www.tampermonkey.net/) は Chrome・Firefox・Safari などのブラウザで動作するユーザースクリプトマネージャーです。
`.user.js` 形式のスクリプトをインストールすることで、Web ページの表示や動作をカスタマイズできます。

このディレクトリは suguruoo-labs における Tampermonkey スクリプト集です。
日常の Web 操作を効率化するスクリプトを管理しています。

---

## 📦 スクリプト一覧

| スクリプト名 | 対象サイト | 概要 |
|---|---|---|
| [get-aws-document-linkTitlePosition](./get-aws-document-linkTitlePosition/) | docs.aws.amazon.com | AWS ドキュメントの H1/H2/H3 タイトル下にコピーボタンを追加。セクションリンクをクリップボードへワンクリックでコピー |

---

## 🚀 Tampermonkey のインストール

### Step 1: ブラウザ拡張をインストール

お使いのブラウザに合わせてインストールしてください。

| ブラウザ | インストール先 |
|---|---|
| Chrome | [Chrome Web Store](https://chromewebstore.google.com/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo) |
| Firefox | [Firefox Add-ons](https://addons.mozilla.org/ja/firefox/addon/tampermonkey/) |
| Safari | [App Store](https://apps.apple.com/jp/app/tampermonkey/id1482490089) |
| Edge | [Edge Add-ons](https://microsoftedge.microsoft.com/addons/detail/tampermonkey/iikmkjmpaadaobahmlepeloendndfphd) |

### Step 2: 各スクリプトをインストール

各スクリプトのディレクトリにある README.md に記載の **インストール方法** を参照してください。

---

## 📁 ディレクトリ構造

```
tampermonkey/
├── README.md                                        # このファイル
└── get-aws-document-linkTitlePosition/
    ├── README.md                                    # 機能説明・バージョン履歴
    └── get-aws-document-linkTitlePosition.user.js  # スクリプト本体
```

新しいスクリプトは `tampermonkey/<script-name>/` の形式でディレクトリを作成し、同様の構成で追加してください。

---

## 🐛 バグ報告・機能要望

バグや改善提案は [Issues](../../issues) に登録してください。

その際、以下の情報を含めると対応がスムーズです：

- **ブラウザ・バージョン**（例：Chrome 130.0）
- **Tampermonkey バージョン**
- **対象スクリプト名**
- **再現手順**
- **期待する動作 / 実際の動作**

---

## 📄 ライセンス

MIT License

