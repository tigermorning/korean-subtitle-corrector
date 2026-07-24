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
  <a href="README.ar.md">العربية</a>
</p>
<!-- lang-switcher:end -->

# Corrector automático de espaciado y ortografía del coreano

Una herramienta que corrige automáticamente el espaciado entre palabras y la ortografía de documentos en coreano de distintos formatos: subtítulos (.srt), texto plano (.txt) y MS Word (.docx). Puede usarse de dos maneras: como CLI o como API web (FastAPI).

Sus decisiones se basan en las normas lingüísticas del Instituto Nacional de la Lengua Coreana, el Diccionario Estándar del Coreano y Urimalsaem (el diccionario abierto). Los casos cuyo fundamento es incierto no se corrigen automáticamente; en su lugar, la herramienta pide confirmación al usuario.

Para más detalles, consulta [PRD.md](./PRD.md) (en coreano).

## Estado

Desarrollo completo. Están implementados tanto la CLI (`main.py`) como la API web (`subtitle_corrector/api.py`, FastAPI + `static/index.html`), y se ha verificado la integración con Supabase (guardar y volver a consultar los resultados de la corrección). Para el despliegue en la nube, consulta [DEPLOY.md](./DEPLOY.md).

## Cómo ejecutar (Windows)

### 1. Preparación

```powershell
git clone https://github.com/tigermorning/korean-subtitle-corrector.git
cd korean-subtitle-corrector
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

Abre `.env` y rellena los siguientes valores (se obtienen gratis en el portal de API abiertas del Instituto Nacional de la Lengua Coreana):

- `STDICT_API_KEY` / `OPENDICT_API_KEY` / `KORNORMS_API_KEY` — Claves de API del Diccionario Estándar del Coreano, de Urimalsaem y de la API de normas lingüísticas del Instituto. Sin ellas el servidor arranca igualmente, pero se produce un error al invocar realmente la función de corrección.
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` — Para guardar los resultados de la corrección (opcional). Aun sin ellas, la corrección funciona con normalidad; solo el guardado se marca como fallido.

### 2. Ejecutar como servidor web (recomendado: se prueba directamente en el navegador)

```powershell
.venv\Scripts\uvicorn subtitle_corrector.api:app --reload
```

Abre http://127.0.0.1:8000 en el navegador → sube un archivo → revisa los resultados de la corrección.

### 3. Ejecutar como CLI

```powershell
.venv\Scripts\python main.py correct examples\sample.srt
```

## Pruebas

```
pip install -r requirements-dev.txt
pytest
```

Las pruebas consultan en tiempo real las API en vivo del Diccionario Estándar del Coreano y de Urimalsaem (no usan respuestas capturadas de forma estática), por lo que `STDICT_API_KEY` / `OPENDICT_API_KEY` deben estar configuradas en `.env` y se necesita conexión a la red. Si fallan, determina primero si se trata de una regresión del código o de una revisión real de los diccionarios del Instituto (consulta PRD.md §5).

> 🤖 Traducido automáticamente del [original en coreano](./README.md); aún no revisado por un hablante nativo.
