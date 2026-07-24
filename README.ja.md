<!-- lang-switcher:start -->
<p align="center">
  <a href="README.md">한국어</a>
  ·
  <a href="README.en.md">English</a>
  ·
  <a href="README.zh-CN.md">中文(简体)</a>
  ·
  <a href="README.zh-TW.md">中文(繁體)</a>
  ·
  <a href="README.es.md">Español</a>
  ·
  <a href="README.ar.md">العربية</a>
</p>
<!-- lang-switcher:end -->

# 韓国語 分かち書き・スペル自動校正ツール

字幕（.srt）／プレーンテキスト（.txt）／MS Word（.docx）など、さまざまな形式の韓国語文書の分かち書き（語の間のスペース）とスペルを自動で校正するツールです。CLI と Web API（FastAPI）の 2 通りの方法で利用できます。

判断は、国立国語院の語文規範・標準国語大辞典・ウリマルセム（開放型辞典）に基づいて行います。根拠が不確かな項目は自動修正せず、ユーザーに確認を求めます。

詳細は [PRD.md](./PRD.md)（韓国語）を参照してください。

## ステータス

開発完了。CLI（`main.py`）と Web API（`subtitle_corrector/api.py`、FastAPI + `static/index.html`）の両方が実装済みで、Supabase 連携（校正結果の保存・再取得）まで確認済みです。クラウドデプロイについては [DEPLOY.md](./DEPLOY.md) を参照してください。

## 実行方法（Windows）

### 1. 準備

```powershell
git clone https://github.com/tigermorning/korean-subtitle-corrector.git
cd korean-subtitle-corrector
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

`.env` を開き、以下の値を入力します（国立国語院のオープン API ポータルで無料発行）：

- `STDICT_API_KEY` / `OPENDICT_API_KEY` / `KORNORMS_API_KEY` — 標準国語大辞典・ウリマルセム・国立国語院 語文規範 API のキー。これらがなくてもサーバーは起動しますが、校正機能を実際に呼び出すとエラーになります。
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` — 校正結果の保存用（任意）。なくても校正自体は正常に動作し、保存だけが失敗として表示されます。

### 2. Web サーバーとして実行（推奨 — ブラウザですぐにテスト可能）

```powershell
.venv\Scripts\uvicorn subtitle_corrector.api:app --reload
```

ブラウザで http://127.0.0.1:8000 にアクセス → ファイルをアップロード → 校正結果を確認。

### 3. CLI として実行

```powershell
.venv\Scripts\python main.py correct examples\sample.srt
```

## テスト

```
pip install -r requirements-dev.txt
pytest
```

テストは標準国語大辞典／ウリマルセムの API をリアルタイムに実際に照会します（静的にキャプチャした応答は使いません）。そのため `.env` に `STDICT_API_KEY` / `OPENDICT_API_KEY` が設定されている必要があり、ネットワーク接続も必要です。失敗した場合は、コードのリグレッションなのか、それとも国立国語院の辞典が実際に改訂されたのかをまず確認してください（PRD.md §5 参照）。

> 🤖 [韓国語の原文](./README.md)から機械翻訳したものです。ネイティブによる校正はまだ行っていません。
