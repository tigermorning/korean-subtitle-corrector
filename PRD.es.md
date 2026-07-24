<!-- lang-switcher:start -->
<p align="center">
  <a href="PRD.md">한국어</a>
  ·
  <a href="PRD.en.md">English</a>
  ·
  <a href="PRD.zh-CN.md">中文(简体)</a>
  ·
  <a href="PRD.zh-TW.md">中文(繁體)</a>
  ·
  <a href="PRD.ja.md">日本語</a>
  ·
  Español
  ·
  <a href="PRD.ar.md">العربية</a>
</p>
<!-- lang-switcher:end -->

# Herramienta CLI de corrección automática de espaciado y ortografía del coreano — PRD (Borrador)

## Estructura del documento (2026-07-24 Modularización)

Este PRD ha crecido demasiado (cerca de 400 líneas), por lo que se dividió de la siguiente manera. Este archivo solo contiene las **especificaciones centrales que rara vez cambian**, mientras que los registros de uso práctico, listas de limitaciones y tablas de verificación que se acumulan con el tiempo se trasladaron a archivos separados.

- **`PRD.md` (este archivo)**: Antecedentes/Propósito, Alcance, Entrada/Salida, Pila tecnológica, Diseño central del motor de juicio de corrección, Flujo de trabajo, Criterios de finalización, Dependencias, Hoja de ruta, TBD.
- **`docs/KNOWN_LIMITATIONS.md`**: Separado de §5. Una lista de falsos positivos/errores descubiertos durante el uso real y sus principios de corrección, así como limitaciones no implementadas registradas por caso (anterior §5 "Limitaciones conocidas / Requisitos de mantenimiento").
- **`docs/IMPLEMENTATION_LOG.md`**: Anterior §13–§27. Un registro que documenta los errores descubiertos durante la corrección real de texto y su historial de corrección en orden cronológico. Si el archivo vuelve a crecer demasiado, el archivo especifica reglas de archivado semestral.
- **`docs/GRAMMAR_PRECEDENTS_TABLE.md`**: Anterior §18. Una tabla de verificación de reglas gramaticales aún no implementadas en código, previamente investigadas a través de Online Gananda.
- **`subtitle_corrector/gananda_precedents.py`**: Precedentes de Online Gananda para expresiones ya manejadas por el código (debe mantenerse junto al código).

Se recomienda que las nuevas sesiones lean los cuatro archivos anteriores en orden después de este archivo. Dado que la automatización (habilidades/tareas programadas) referencia estas rutas exactas, si esta estructura cambia, la siguiente lista también debe actualizarse: 4 habilidades en `.claude/skills/`, `~/.claude/scheduled-tasks/gananda-precedent-research/SKILL.md`, `AGENTS.md`, y el archivo espejo `C:\Users\user\Documents\자막_맞춤법교정_PRD.md`.

## Notas de transferencia de sesión (Lea esto primero cuando continúe con otra herramienta de codificación IA)

- **Principio central**: "Basado en referencias normativas autoritativas, no en conjeturas probabilísticas — cuando haya duda, siempre pida confirmación al usuario". No sugiera siquiera automatización que viole este principio (por ejemplo, juzgar basándose en inferencia de contexto). Toda la lista en `docs/KNOWN_LIMITATIONS.md` es un registro de errores y decisiones de diseño descubridos/corregidos al intentar defender este principio, así que revíselo antes de agregar nuevas funciones.
- **Lo que se ha implementado hasta ahora**: Notación de palabras extranjeras (kornorms, autocorrección de términos generales / nombres propios siempre marcados para confirmación), ortografía (Diccionario Estándar del Coreano + Urimalsaem, verificando solo NNG/VV/VA), espaciado (combinaciones de partículas/terminaciones corregidas automáticamente, sustantivos compuestos/sustantivos dependientes/verbos auxiliares corregidos automáticamente cuando hay evidencia del diccionario, de lo contrario marcados, espaciado de verbos auxiliares unificado según reglas), patrones de errores confirmados/autocorrección de expresiones discriminatorias, marcado de expresiones depuradas. Para detalles y el historial de descubrimiento de cada error, consulte `docs/KNOWN_LIMITATIONS.md` y `docs/IMPLEMENTATION_LOG.md`. **API web + Almacenamiento (§11, implementado 2026-07-16)**: `subtitle_corrector/api.py` (FastAPI) reutiliza el mismo motor (`engine.correct_entries`) que la CLI para carga `.srt`/`.txt`/`.docx` → resultados guardados en Supabase, `static/index.html` sirve como pantalla de carga y pantalla de visualización de resultados (con campos de entrada para nombres propios/nombres de platos). Solo se completaron pruebas locales; el despliegue real en Supabase/Render requiere que el usuario siga `DEPLOY.md` manualmente (no se pueden crear cuentas). **Resultado del intento de despliegue en Render 2026-07-22: la carga de memoria del modelo kiwipiepy (aprox. 310MB) casi agota el límite gratuito de 512MB, causando errores 502 — este intento de despliegue se ha pospuesto** (consulte `docs/RETROSPECTIVE.md`). La siguiente sesión debe confirmar primero si reintentar el despliegue. Consulte `docs/IMPLEMENTATION_LOG.md` §13: el problema de kiwi dividir incorrectamente palabras desconocidas (nombres propios/nombres de platos) se resolvió con `register_custom_words()` (kiwi.add_user_word).
- **Tarea pendiente más grande**: **Integración de Online Gananda (Fase 2, no implementada)** — Una función para complementar notaciones ambiguas que no se pueden resolver ni siquiera con diccionario/referencias normativas (Fase 1) usando el archivo de respuestas pasadas del Instituto Nacional de la Lengua Coreana en Online Gananda. Dado que es un foro de preguntas y respuestas sin una API limpia, el método de búsqueda/rastreo debe investigarse primero, y el alcance es bastante grande (consulte la lista de dependencias §8).
- **Tarea inmediata siguiente (pendiente de inicio, guardada 2026-07-21)**: Investigación/implementación de falsos positivos de "sustantivo+드리다" (por ejemplo, 부탁드리다) en `docs/IMPLEMENTATION_LOG.md` §27 — aún no comenzada, pospuesta considerando el consumo de tokens, para proceder cuando el usuario lo solicite. Para continuar esta tarea en la siguiente sesión, lea §27 completo primero.
- **Consulte `docs/KNOWN_LIMITATIONS.md`**: Tres falsos positivos severos descubiertos durante el uso real (reemplazo de expresiones discriminatorias afectando incorrectamente palabras no relacionadas, espaciado de verbos auxiliares forzando la separación de verbos compuestos registrados en el diccionario, etiquetado falso de "요" por kiwi) se han corregido a nivel de patrón. Tenga cuidado de no introducir errores similares del tipo "reemplazar basándose solo en caracteres" o "forzar reglas sin verificación del diccionario" en el futuro.
- **Elementos a pequeña escala que se pueden impulsar**: Promoción de la autocorrección de notación numérica §44 ("몇만/몇백만"). (Los 6 elementos restantes de sustantivos dependientes del §42 tienen tablas de verificación completadas en `docs/GRAMMAR_PRECEDENTS_TABLE.md`, pero la implementación real del código aún no se ha realizado).
- **Método de trabajo (debe seguirse)**: No mire solo el código y diga "está listo" — ejecute `main.py correct` con texto real (artículos de noticias, publicaciones de blogs, etc. — los originales con derechos de autor se mantienen solo en el scratchpad y no se comprometen en el repositorio) para verificar. Este enfoque ha detectado errores reales múltiples veces (consulte cada elemento en `docs/IMPLEMENTATION_LOG.md`). La prueba de regresión usa `examples/sample.srt` como fixture básico.
- **Convenio post-completado**: Cuando termine una función: (1) verificación de regresión con `examples/sample.srt` → (2) sincronizar `PRD.md` y `docs/*.md` relacionados, más el archivo espejo `C:\Users\user\Documents\자막_맞춤법교정_PRD.md` → (3) git commit. Los mensajes de commit mantienen el estilo de ser específicos sobre "por qué" y "qué error se corrigió" (consulte git log). **El git commit está automatizado para este proyecto (2026-07-17, instrucción del usuario) — commitee automáticamente cuando esté completo sin solicitudes separadas. Sin embargo, git push no está incluido y siempre requiere aprobación explícita.** (Excepción: la ejecución no tripulada como la tarea programada `gananda-precedent-research` sigue las instrucciones del propio archivo de tarea (sin commits) ya que un humano no ha revisado los resultados).

## 1. Antecedentes y propósito

Las principales frustraciones al usar la herramienta de autocorrección coreana existente 'Verificador de Ortografía de la Universidad de Pusan' eran cuatro: **demasiados falsos positivos (marcar incorrectamente expresiones normales y nombres propios como errores), exigir correcciones sin proporcionar ninguna base para por qué estaba mal, las propias sugerencias de corrección pareciendo inconsistentes y aleatorias — haciéndolas sentir como nuevos errores, y límites de caracteres que impedían verificar documentos largos en una sola pasada.**

Este proyecto aborda directamente estos cuatro problemas: consulta en tiempo real del Diccionario Estándar del Coreano, Urimalsaem y las normas lingüísticas del Instituto Nacional de la Lengua Coreana para documentar claramente la base de los juicios (siempre especificando la base en las razones de las banderas), corrigiendo automáticamente solo los elementos con evidencia firme, dejando los elementos ambiguos o aquellos que dependen del contexto a la revisión humana en lugar de corregir aleatoriamente, y cargando archivos de documento completos sin límites de caracteres para procesamiento en una sola pasada — de las cuales la v1 se enfoca en **corrección de espaciado y ortografía**.

**Objetivo**: Lograr cero errores en los elementos corregidos automáticamente basándose en referencias normativas lingüísticas autoritativas, no en conjeturas probabilísticas. Nunca corrija casualmente elementos con evidencia incierta — páselos a humanos.

**Usuarios objetivo**: Traductores profesionales. El propósito es reducir la carga de su trabajo repetitivo de corrección de espaciado y ortografía. Por lo tanto, tanto los falsos positivos (marcar texto normal como incorrecto) como las omisiones (perder errores reales) contradicen este propósito — los falsos positivos hacen que los traductores pierdan tiempo innecesario en corrección, mientras que las omisiones dejan exactamente el esfuerzo que la herramienta pretendía aliviar. Es por esto que el principio de "automatizar solo lo que está seguro, siempre delegar la ambigüedad a humanos" es especialmente importante.

## 2. Alcance (v1)

- **Funciones**: Corrección de espaciado + corrección ortográfica para texto coreano
- **Objetivos**: Documentos coreanos en varios formatos — texto plano (.txt), MS Word (.docx), subtítulos (.srt). Los archivos de subtítulos son solo uno de los formatos soportados; esta herramienta no es exclusivamente para trabajo de subtítulos.
- **Idioma objetivo**: **Coreano exclusivamente**

### Elementos postponidos a v2 (Fuera de alcance)
- Verificación de naturalidad/precisión de texto traducido (requiere comparación con el original/juicio de estilo de traducción, que no se puede verificar con el criterio de esta herramienta de "referencias normativas autoritativas" — consulte `docs/IMPLEMENTATION_LOG.md` §13)

## 3. Entrada / Salida

- **Entrada**: Archivos de subtítulos (.srt), texto plano (.txt), MS Word (.docx)
- **Salida**:
  - Archivo de resultado corregido (manteniendo el mismo formato que el original — .srt preserva incluso los códigos de tiempo)
  - Archivo de reporte de banderas (lista de elementos demasiado ambiguos para corregir automáticamente)

## 4. Forma de uso y pila tecnológica

- **Herramienta CLI**
- **Lenguaje de desarrollo**: **Python**
- **Framework CLI: Typer**
  - La estructura requiere al menos 2 subcomandos (`correct`: ejecutar corrección de texto, `apply-report`: reaplicar reportes completados por el usuario al original), lo que hace que la gestión de subcomandos sea más fácil que argparse
  - Basado en type hints, lo cual funciona bien con este proyecto que maneja estructuras de datos claras como las respuestas de la API del Instituto Nacional de la Lengua Coreana
  - Basado en Click, manteniendo estabilidad mientras reduce boilerplate
  - Sigue las convenciones para futura distribución pip

### Principios de arquitectura (consideración para extensión futura)

La lógica de corrección (consulta de diccionario/normativo, generación de juicios/banderas) está diseñada como un **módulo de biblioteca puro separado de la CLI**. La CLI (Typer) sirve solo como una interfaz delgada que llama a esta biblioteca. Esto permite que el mismo motor de corrección se reutilice en un servidor API durante la expansión del backend §9 (sin necesidad de reescribir el código CLI). En la etapa v1 no se implementa el backend directamente — lo que se construye es estrictamente una herramienta CLI local.

## 5. Motor de juicio de corrección (Diseño central)

Al encontrar una oración ambigua, se juzga en el siguiente orden, y si no se puede estar seguro hasta el final, **se marca sin corregir automáticamente** (el principio de que un estado no corregido es mejor que una corrección incorrecta).

1. **Juicio primario — Base normativa/diccionario**
   - Diccionario Estándar del Coreano, Urimalsaem (API abierta del Instituto Nacional de la Lengua Coreana, `search.do`) — Verificar existencia de entrada
   - Distinguir palabras compuestas (notación con guión, tiene categoría gramatical → siempre unidas) de frases sustantivas (notación con caret, `pos: "sin categoría gramatical"` → principios de espaciado/unión permitida) usando los campos `word`/`pos` de la respuesta `search.do` del Diccionario Estándar del Coreano. Las palabras compuestas perdidas por kiwi.space() (por ejemplo, "노천 카페" → no corregido) se complementan con autocorrección basada en diccionario (`compound_status()`, `correct_compound_spacing()`, implementado)
   - API de contenido del Diccionario Estándar del coreano (`view.do`) — Verificar casos de uso, base de ortografía coreana (`norm_info`) adjunta a algunas palabras (aún no implementado)
   - API abierta de normas lingüísticas coreanas (`kornorms/exampleReqList.do`) — Consultar ejemplos de notación de palabras extranjeras/romanización oficialmente confirmados por el Instituto Nacional de la Lengua Coreana (notación coreana ↔ notación original, nombres personales/lugares/términos generales). Se necesita nueva clave API
   - Texto original de reglas de notación de palabras extranjeras (sitio web de normas lingüísticas del Instituto Nacional de la Lengua Coreana, 5 principios básicos de notación + detalles de notación por idioma) — Documentos estáticos sin API. Solo como último recurso para palabras extranjeras completamente nuevas (neologismos sin notación oficial) que no están en la API kornorms. Si aún es ambigua, pasar a fase 3

2. **Juicio secundario — Archivo de respuestas de Online Gananda**
   - Online Gananda no es una API en tiempo real sino un foro donde personas responden directamente, por lo que no se hacen consultas en tiempo real
   - En su lugar, se utiliza **solo buscando/referenciando archivos de respuestas pasadas ya públicas** (los precedentes acumulados están en `subtitle_corrector/gananda_precedents.py`, la gramática pendiente aún no convertida a código está en `docs/GRAMMAR_PRECEDENTS_TABLE.md`)

3. **Terciario — Aún ambigua → Delegar a humano**
   - Corrección automática prohibida, marcar en reporte

### Principio central: "Los datos del diccionario en tiempo real siempre tienen prioridad"

Los resultados de las consultas en tiempo real de la API del Diccionario Estándar del Coreano/Urimalsaem siempre tienen prioridad sobre las suposiciones codificadas en el código o el contenido de materiales educativos aprendidos previamente. Las regulaciones/diccionarios se revisan, por lo que no fije valores codificados en el código asumiendo "se confirmó antes, así que es correcto" — realice consultas cada vez que se necesite juicio. Por qué este principio es necesario en la práctica (un caso donde una suposición codificada se desactualizó y causó un error real) se puede encontrar en `docs/IMPLEMENTATION_LOG.md` §17 "Reemplazo de suposiciones de verificación codificadas con consultas en tiempo real".

### Principio de trabajo: "Tabla de verificación primero, código después" (Confirmado 2026-07-17)

Al trabajar en `correct_aux_verb_spacing()` patrón 2 (tipo "할만하다"), el enfoque de escribir el código primero y parchear excepciones cuando se descubrían resultó en que el usuario señalara el mismo error dos veces con ejemplos reales de Urimalsaem ("할만하다" se corrigió incorrectamente a "할 만 하다"). La causa estaba en el orden mismo — escribir código primero basado en la suposición de "la regla debería ser así" y luego verificar contra el diccionario.

**Al agregar reglas nuevas (especialmente patrones gramaticales que pueden tener excepciones) en el futuro, se debe seguir este orden** (para procedimientos específicos consulte `.claude/skills/grammar-rule-verify-then-code/SKILL.md`):
1. Primero consulte todos los casos posibles (todas las expresiones que podrían encajar en el patrón, hasta precedentes del Diccionario Estándar del Coreano/Urimalsaem/kornorms/Online Gananda de §5-1/2/3) directamente a través de las APIs del diccionario para crear una **tabla de verificación (qué entrada → qué respuesta correcta)**.
2. Escriba código que coincida exactamente con la tabla — el código sigue la tabla, no la tabla verifica el código retroactivamente.
3. Si después de la implementación se descubren casos nuevos no en la tabla, no parchee el código temporalmente — primero agregue el caso a la tabla (reconsulte el diccionario) y luego corrija el código para coincidir con la tabla.

### Limitaciones conocidas / Requisitos de mantenimiento

La lista completa de falsos positivos/errores específicos descubiertos durante el uso real y sus principios de corrección, así como limitaciones no implementadas, se ha movido a `docs/KNOWN_LIMITATIONS.md` — revíselo antes de agregar nuevas funciones.

## 6. Flujo de trabajo de banderas y reaplicación (Implementado — `correct` / `apply-report`)

1. Procesar el archivo de subtítulos completo
2. Corregir automáticamente los elementos con confianza firme de inmediato
3. Los elementos ambiguos no se interrumpen durante la ejecución; después de completar todo el procesamiento, se **recopilan y producen en un solo archivo de reporte** (número de línea + texto + referencia). Para elementos como nombres personales/lugares que se aplicaron automáticamente pero necesitan doble verificación, el reporte incluye qué se cambió y por qué junto con el texto del resultado ya aplicado.
4. El usuario ingresa valores de corrección directamente en el archivo de reporte
5. Cuando se vuelve a ejecutar el programa, los valores ingresados por el usuario se **aplican automáticamente al archivo de subtítulos original**

## 7. Criterios de finalización / Método de verificación

- **Método de verificación**: Medición de precisión contra un conjunto de prueba con respuestas correctas etiquetadas por humanos
  - Objetivo: Cero errores en los elementos corregidos automáticamente (sin banderas) por el programa
- **Fuente del conjunto de prueba**: Recopilados/creados directamente (reuniendo videos reales de YouTube/resultados STT y etiquetando respuestas correctas)

## 8. Dependencias / Trabajos previos

- [x] Solicitud de clave API abierta del Instituto Nacional de la Lengua Coreana (Diccionario Estándar del Coreano, Urimalsaem)
- [x] Solicitud de clave API abierta de normas lingüísticas coreanas (kornorms, ejemplos de notación de palabras extranjeras/romanización)
- [x] Acumulación de precedentes de Online Gananda — Implementada investigando casos realmente utilizados en lotes en lugar de rastreo completo (consulte `docs/IMPLEMENTATION_LOG.md` §17)
- [ ] Recolección de conjunto de prueba y etiquetado de respuestas correctas

## 9. Hoja de ruta de extensión futura (después de v1)

Lo que estamos construyendo ahora es una herramienta CLI local, pero los siguientes elementos se dejan como hoja de ruta considerando la posibilidad de expansión futura a forma de servicio (web/backend). El diseño de v1 solo refleja los "Principios de arquitectura" §4 (separación del motor de corrección e interfaz), no las funciones mismas.

- **Login/Cuenta**: Necesario para gestionar el historial de procesamiento por usuario. El método de autenticación (implementación propia vs OAuth, etc.) está indeterminado. Aún no implementado — el almacenamiento §11 funciona sin login al nivel de "cualquiera que sepa el ID puede ver el resultado" (nivel de seguridad de enlace corto compartido). Esto debe implementarse antes de gestionar múltiples usuarios por separado.
- **Almacenamiento — Implementado (2026-07-16, consulte §11)**: Los resultados de corrección y reportes de banderas de documentos cargados se almacenan en Supabase (Postgres). La política de duración de almacenamiento/manejo de información personal (contenido del documento) aún no se ha determinado (actualmente indefinida) — se debe decidir al pasar a servicio real.
- **Pago**: Plan de pago/facturación por uso. Qué funciones se monetizarán (por ejemplo, volumen de procesamiento, llamadas a API de ortografía) está indeterminado.
- **Diccionarios de terminología por dominio**: Corrección de términos especializados en campos específicos (medicina, derecho, etc.) como diccionario de terminología médica (KMLE). Dado que son sitios privados y no la API abierta oficial del Instituto Nacional de la Lengua Coreana, se debe verificar primero los términos de uso, y cae fuera del alcance de v1 de texto coreano general, por lo que se pospone para después de v2.
- Cuando esta hoja de ruta se concrete, se separará en un PRD separado (arquitectura backend, autenticación, integración de pago están fuera del alcance de este documento).

## 10. TBD (Decisiones pendientes para después)

- Horario de desarrollo / período objetivo
- Método de despliegue (paquete pip, etc.)
- Especificación de formato exacta del archivo de reporte (json/csv, etc.)
- Objetivos de rendimiento como velocidad de procesamiento
- Arquitectura detallada de módulos, política de manejo de errores

## 11. API web / Almacenamiento (Implementado, 2026-07-16)

Como tarea de clase ("Agregar backend a mi servicio"), el elemento "Almacenamiento" de §9 se implementó realmente. No se agregó nueva lógica de corrección; se llama directamente al motor existente siguiendo los principios de arquitectura de §4.

- **Composición**: `subtitle_corrector/api.py` (FastAPI) — `POST /api/correct` (carga `.srt` → `parsers.parse_srt` → `engine.correct_entries` → guardar resultados) / `GET /api/reports/{id}` (recuperar resultados guardados). `static/index.html` sirve como pantalla de carga y pantalla de visualización de resultados (`?id=` para actualización/mantenimiento de resultados en otros dispositivos).
- **Almacenamiento**: Supabase (Postgres), `subtitle_corrector/store.py` llama directamente REST (PostgREST) a través de `requests`. El esquema de tabla está en `supabase_schema.sql`.
- **Diseño de seguridad — La estructura que este proyecto eligió NO es el patrón de "el navegador accede directamente a Supabase" de los materiales de clase**: El navegador solo solicita a este servidor FastAPI y nunca accede directamente a Supabase. Por lo tanto, es seguro tener solo `SUPABASE_SERVICE_KEY` (clave de administrador, ignora RLS) como variable de entorno del lado del servidor, y la tabla `reports` tiene RLS habilitado sin crear políticas, por lo que la clave anon (pública) rechaza todas las solicitudes — el servidor es la única ruta de acceso.
- **Secretos**: `STDICT_API_KEY`/`OPENDICT_API_KEY`/`KORNORMS_API_KEY` (existentes) + `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` (nuevos), todos existen solo en `.env` (local) / variables de entorno de Render (despliegue). Consulte `.env.example`.
- **Despliegue**: Se intentó desplegar FastAPI directamente en Render (servicio web gratuito). La creación de cuenta/configuración del panel de control debe ser realizada por el usuario (la IA no puede iniciar sesión), por lo que los pasos están organizados en `DEPLOY.md`. **Resultado del intento de despliegue real 2026-07-22: el uso de memoria del modelo kiwipiepy (aprox. 310MB) casi agota el límite gratuito de 512MB, causando errores 502 — este intento de despliegue se ha pospuesto** (consulte `docs/RETROSPECTIVE.md`). Las pruebas locales (verificación de integración del motor con almacenamiento stub) y la integración real de Supabase (2026-07-16, el usuario creó la cuenta) se completaron.
- **Pruebas**: Las rutas FastAPI (200/404, validación de formato de archivo) y la integración del motor se verificaron con `examples/sample.srt` (`store.save_report`/`get_report` reemplazados por stubs para verificación sin cuenta real de Supabase).
- **4 errores de uso real relacionados con API web/Almacenamiento, falsos positivos de palabras no registradas de kiwi, revisión integral de seguridad/SQL, aislamiento de fallos de almacenamiento, etc.**: Para el historial detallado, consulte `docs/IMPLEMENTATION_LOG.md` (elementos relacionados con §11, §13, §24, §25).