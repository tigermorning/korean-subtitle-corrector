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
  <a href="README.ja.md">日本語</a>
  ·
  <a href="README.es.md">Español</a>
</p>
<!-- lang-switcher:end -->

# أداة التصحيح التلقائي للتباعد والإملاء في اللغة الكورية

أداة تُصحِّح تلقائيًا التباعد بين الكلمات والإملاء في المستندات الكورية بمختلف الصيغ — ملفات الترجمة (.srt)، والنص العادي (.txt)، وMS Word (.docx). يمكن استخدامها بطريقتين: كواجهة سطر أوامر (CLI) أو كواجهة برمجة تطبيقات ويب (FastAPI).

تعتمد قراراتها على القواعد اللغوية للمعهد الوطني للغة الكورية، والمعجم الكوري القياسي، ومعجم «أوريمالسايم» (Urimalsaem، المعجم المفتوح). أمّا العناصر التي يكون أساسها غير مؤكَّد فلا تُصحَّح تلقائيًا؛ بل تطلب الأداة من المستخدم تأكيدها.

للتفاصيل، انظر [PRD.md](./PRD.md) (بالكورية).

## الحالة

اكتمل التطوير. جرى تنفيذ كلٍّ من واجهة سطر الأوامر (`main.py`) وواجهة برمجة تطبيقات الويب (`subtitle_corrector/api.py`، FastAPI + `static/index.html`)، كما جرى التحقّق من تكامل Supabase (حفظ نتائج التصحيح وإعادة الاستعلام عنها). للنشر السحابي، انظر [DEPLOY.md](./DEPLOY.md).

## طريقة التشغيل (Windows)

### 1. التهيئة

```powershell
git clone https://github.com/tigermorning/korean-subtitle-corrector.git
cd korean-subtitle-corrector
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

افتح الملف `.env` واملأ القيم التالية (تُصدَر مجانًا من بوّابة واجهات برمجة التطبيقات المفتوحة التابعة للمعهد الوطني للغة الكورية):

- `STDICT_API_KEY` / `OPENDICT_API_KEY` / `KORNORMS_API_KEY` — مفاتيح واجهات برمجة التطبيقات للمعجم الكوري القياسي، وأوريمالسايم، وواجهة القواعد اللغوية للمعهد. بدونها يعمل الخادم مع ذلك، لكن يحدث خطأ عند الاستدعاء الفعلي لوظيفة التصحيح.
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` — لحفظ نتائج التصحيح (اختياري). حتى بدونها يعمل التصحيح نفسه بشكل طبيعي؛ وتُعلَّم خطوة الحفظ وحدها بأنها فشلت.

### 2. التشغيل كخادم ويب (مُوصى به — يمكن اختباره مباشرةً في المتصفّح)

```powershell
.venv\Scripts\uvicorn subtitle_corrector.api:app --reload
```

افتح http://127.0.0.1:8000 في المتصفّح ← ارفع ملفًا ← تحقّق من نتائج التصحيح.

### 3. التشغيل كواجهة سطر أوامر

```powershell
.venv\Scripts\python main.py correct examples\sample.srt
```

## الاختبارات

```
pip install -r requirements-dev.txt
pytest
```

تستعلم الاختبارات عن واجهات المعجم الكوري القياسي/أوريمالسايم الحيّة في الوقت الفعلي (ولا تستخدم استجابات مُخزَّنة مسبقًا بشكل ثابت)، لذا يجب ضبط `STDICT_API_KEY` / `OPENDICT_API_KEY` في `.env`، ويلزم الاتصال بالشبكة. إذا فشلت، فحدِّد أوّلًا ما إذا كان الأمر تراجعًا في الشيفرة (regression) أم تنقيحًا فعليًا لمعاجم المعهد (انظر PRD.md §5).

> 🤖 تُرجمت آليًا من [الأصل الكوري](./README.md)؛ ولم يراجعها ناطق أصلي بعد.
