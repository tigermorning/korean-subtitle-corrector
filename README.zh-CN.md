<!-- lang-switcher:start -->
<p align="center">
  <a href="README.md">한국어</a>
  ·
  <a href="README.en.md">English</a>
  ·
  <a href="README.zh-TW.md">中文(繁體)</a>
  ·
  <a href="README.ja.md">日本語</a>
  ·
  <a href="README.es.md">Español</a>
  ·
  <a href="README.ar.md">العربية</a>
</p>
<!-- lang-switcher:end -->

# 韩语分写·拼写自动校对工具

一款自动校对多种格式韩语文档分写（词间空格）与拼写的工具，支持字幕（.srt）、纯文本（.txt）、MS Word（.docx）等格式。可通过两种方式使用：命令行（CLI）和网页 API（FastAPI）。

工具依据韩国国立国语院的语文规范、《标准国语大词典》和《우리말샘》（开放词典）进行判断；对于依据不明确的项目，不会自动修改，而是请用户确认。

详情请参阅 [PRD.md](./PRD.md)（韩语）。

## 状态

开发完成。命令行（`main.py`）与网页 API（`subtitle_corrector/api.py`，FastAPI + `static/index.html`）均已实现，并已验证 Supabase 集成（保存/重新查询校对结果）。云端部署请参阅 [DEPLOY.md](./DEPLOY.md)。

## 运行方法（Windows）

### 1. 准备

```powershell
git clone https://github.com/tigermorning/korean-subtitle-corrector.git
cd korean-subtitle-corrector
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

打开 `.env`，填入以下值（在韩国国立国语院的开放 API 门户免费申请）：

- `STDICT_API_KEY` / `OPENDICT_API_KEY` / `KORNORMS_API_KEY` —《标准国语大词典》《우리말샘》以及国立国语院语文规范 API 的密钥。缺少这些密钥时服务器仍可启动，但在实际调用校对功能时会报错。
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` — 用于保存校对结果（可选）。即使没有它们，校对本身也能正常工作，只是保存步骤会显示为失败。

### 2. 以网页服务器方式运行（推荐——可直接在浏览器中测试）

```powershell
.venv\Scripts\uvicorn subtitle_corrector.api:app --reload
```

在浏览器中访问 http://127.0.0.1:8000 → 上传文件 → 查看校对结果。

### 3. 以命令行方式运行

```powershell
.venv\Scripts\python main.py correct examples\sample.srt
```

## 测试

```
pip install -r requirements-dev.txt
pytest
```

测试会实时查询在线的《标准国语大词典》/《우리말샘》API（不使用静态缓存的响应），因此 `.env` 中必须设置 `STDICT_API_KEY` / `OPENDICT_API_KEY`，并且需要联网。若测试失败，请先判断是代码回归，还是国立国语院词典确实发生了修订（参阅 PRD.md §5）。

> 🤖 由[韩语原文](./README.md)机器翻译，尚未经母语者校对。
