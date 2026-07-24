<!-- lang-switcher:start -->
<p align="center">
  <a href="README.md">한국어</a>
  ·
  <a href="README.en.md">English</a>
  ·
  <a href="README.zh-CN.md">中文(简体)</a>
  ·
  <a href="README.ja.md">日本語</a>
  ·
  <a href="README.es.md">Español</a>
  ·
  <a href="README.ar.md">العربية</a>
</p>
<!-- lang-switcher:end -->

# 韓語分寫·拼寫自動校對工具

一款自動校對多種格式韓語文件分寫（詞間空格）與拼寫的工具，支援字幕（.srt）、純文字（.txt）、MS Word（.docx）等格式。可透過兩種方式使用：命令列（CLI）與網頁 API（FastAPI）。

工具依據韓國國立國語院的語文規範、《標準國語大辭典》與《우리말샘》（開放辭典）進行判斷；對於依據不明確的項目，不會自動修改，而是請使用者確認。

詳情請參閱 [PRD.md](./PRD.md)（韓語）。

## 狀態

開發完成。命令列（`main.py`）與網頁 API（`subtitle_corrector/api.py`，FastAPI + `static/index.html`）皆已實作，並已驗證 Supabase 整合（儲存/重新查詢校對結果）。雲端部署請參閱 [DEPLOY.md](./DEPLOY.md)。

## 執行方法（Windows）

### 1. 準備

```powershell
git clone https://github.com/tigermorning/korean-subtitle-corrector.git
cd korean-subtitle-corrector
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

開啟 `.env`，填入以下數值（於韓國國立國語院的開放 API 入口免費申請）：

- `STDICT_API_KEY` / `OPENDICT_API_KEY` / `KORNORMS_API_KEY` —《標準國語大辭典》《우리말샘》以及國立國語院語文規範 API 的金鑰。缺少這些金鑰時伺服器仍可啟動，但在實際呼叫校對功能時會發生錯誤。
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` — 用於儲存校對結果（選用）。即使沒有它們，校對本身仍可正常運作，只是儲存步驟會顯示為失敗。

### 2. 以網頁伺服器方式執行（推薦——可直接在瀏覽器中測試）

```powershell
.venv\Scripts\uvicorn subtitle_corrector.api:app --reload
```

在瀏覽器中開啟 http://127.0.0.1:8000 → 上傳檔案 → 查看校對結果。

### 3. 以命令列方式執行

```powershell
.venv\Scripts\python main.py correct examples\sample.srt
```

## 測試

```
pip install -r requirements-dev.txt
pytest
```

測試會即時查詢線上的《標準國語大辭典》/《우리말샘》API（不使用預先擷取的靜態回應），因此 `.env` 中必須設定 `STDICT_API_KEY` / `OPENDICT_API_KEY`，並且需要連網。若測試失敗，請先判斷是程式碼迴歸，還是國立國語院辭典確實發生了修訂（參閱 PRD.md §5）。

> 🤖 由[韓語原文](./README.md)機器翻譯，尚未經母語者校對。
