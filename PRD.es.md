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
  <a href="PRD.ar.md">العربية</a>
</p>
<!-- lang-switcher:end -->

# Herramienta CLI de corrección automática de espaciado y ortografía del coreano — PRD (borrador)

## Estructura del documento (modularización 2026-07-24)

Este PRD ha crecido demasiado (casi 400 líneas), así que se dividió de la siguiente manera. Este archivo conserva ahora solo las **especificaciones centrales que rara vez cambian**, mientras que los registros de uso real, las listas de limitaciones y las tablas de verificación que se acumulan con el tiempo se trasladaron a archivos separados.

- **`PRD.md` (este archivo)**: contexto/objetivo, alcance, entrada/salida, stack tecnológico, diseño central del motor de decisión de corrección, flujo de trabajo, criterios de finalización, dependencias, hoja de ruta, TBD.
- **`docs/KNOWN_LIMITATIONS.md`**: separado de §5. Una lista de falsos positivos/errores descubiertos durante el uso real y sus principios de corrección, así como las limitaciones aún no implementadas, registradas caso por caso (antiguo §5 "Limitaciones conocidas / requisitos de mantenimiento").
- **`docs/IMPLEMENTATION_LOG.md`**: antiguos §13–§27. Un registro que documenta, en orden cronológico, los errores descubiertos al revisar texto real y el historial de sus correcciones. Si el archivo vuelve a crecer demasiado, el propio archivo especifica las reglas para archivarlo semestralmente.
- **`docs/GRAMMAR_PRECEDENTS_TABLE.md`**: antiguo §18. Una tabla de verificación de reglas gramaticales aún no implementadas en el código, investigadas por adelantado mediante Online Ganada.
- **`subtitle_corrector/gananda_precedents.py`**: precedentes de Online Ganada para expresiones que el código ya maneja (deben mantenerse junto al código).

Se recomienda que las nuevas sesiones revisen los cuatro archivos anteriores en orden después de este archivo. Dado que la automatización (skills/tareas programadas) hace referencia a estas rutas exactas, si se vuelve a cambiar esta estructura, también se debe actualizar la siguiente lista: los 4 skills en `.claude/skills/`, `~/.claude/scheduled-tasks/gananda-precedent-research/SKILL.md`, `AGENTS.md` y el archivo espejo `C:\Users\user\Documents\자막_맞춤법교정_PRD.md`.

## Notas de transferencia de sesión (léelas primero al continuar con otra herramienta de codificación con IA)

- **Principio central**: "Basado en referencias normativas autoritativas, no en conjeturas probabilísticas — cuando haya dudas, pregunta siempre al usuario para confirmar." No sugieras siquiera una automatización que viole este principio (por ejemplo, juzgar basándose en inferencia de contexto). Toda la lista en `docs/KNOWN_LIMITATIONS.md` es un registro de errores y decisiones de diseño descubiertos/corregidos al intentar mantener este principio, así que revísala antes de añadir nuevas funciones.
- **Lo que se ha implementado hasta ahora**: notación de extranjerismos (kornorms, autocorrección de términos generales / los nombres propios siempre se marcan para confirmación), ortografía (Diccionario Estándar del Coreano + Urimalsaem, comprobando solo NNG/VV/VA), espaciado entre palabras (las combinaciones de partícula/terminación se autocorrigen, los compuestos/sustantivos dependientes/verbos auxiliares se autocorrigen cuando existe evidencia en el diccionario y, si no, se marcan; el espaciado de verbos auxiliares se unifica automáticamente según las reglas), autocorrección de patrones de error confirmados/expresiones discriminatorias, marcado de expresiones depuradas. Para más detalles y el historial de descubrimiento de cada error, consulta `docs/KNOWN_LIMITATIONS.md` y `docs/IMPLEMENTATION_LOG.md`. **API web + almacenamiento (§11, implementado 2026-07-16)**: `subtitle_corrector/api.py` (FastAPI) reutiliza el mismo motor (`engine.correct_entries`) que la CLI para la carga de `.srt`/`.txt`/`.docx` → los resultados de corrección se guardan en Supabase, y `static/index.html` sirve tanto de pantalla de carga como de pantalla de consulta de resultados (con campos de entrada para nombres propios/nombres de platos). Solo se completaron las pruebas locales; el despliegue real en Supabase/Render lo debe realizar el usuario manualmente siguiendo `DEPLOY.md` (la IA no puede crear cuentas). **Resultado del intento de despliegue en Render del 2026-07-22: solo la carga del modelo de kiwipiepy consume unos 310MB, llenando casi por completo el límite de 512MB del nivel gratuito y provocando errores 502 — se decidió posponer el despliegue en sí** (consulta `docs/RETROSPECTIVE.md`). La próxima sesión debería confirmar primero si se reintenta el despliegue. Consulta `docs/IMPLEMENTATION_LOG.md` §13: el problema de que kiwi dividiera incorrectamente palabras desconocidas (nombres propios, nombres de platos) se resolvió con `register_custom_words()` (kiwi.add_user_word).
- **La tarea pendiente más grande**: **integración de Online Ganada (fase 2, sin implementar)** — una función para complementar las notaciones ambiguas que no pueden resolverse ni siquiera con las referencias de diccionario/normativas (fase 1), usando el archivo de respuestas pasadas de Online Ganada del Instituto Nacional de la Lengua Coreana. Como es un tablón de preguntas y respuestas sin una API limpia, primero hay que investigar el método de búsqueda/rastreo, y el alcance es bastante grande (consulta la lista de dependencias de §8).
- **Tarea siguiente inmediata (a la espera de comenzar, guardada el 2026-07-21)**: investigación/implementación de los falsos positivos de "sustantivo+드리다" (por ejemplo, 부탁드리다) en `docs/IMPLEMENTATION_LOG.md` §27 — aún no comenzada, pospuesta considerando el consumo de tokens, a realizar cuando el usuario lo solicite. Para continuar esta tarea en la próxima sesión, lee primero todo el §27.
- **Consulta `docs/KNOWN_LIMITATIONS.md`**: tres falsos positivos graves descubiertos durante el uso real (la sustitución de expresiones discriminatorias afectando incorrectamente a palabras no relacionadas, el espaciado de verbos auxiliares dividiendo a la fuerza verbos compuestos registrados en el diccionario, el etiquetado erróneo de "요" por parte de kiwi) se corrigieron todos a nivel de patrón. Ten cuidado de no introducir en el futuro errores similares del tipo "sustituir basándose solo en los caracteres" o "imponer reglas sin verificación en el diccionario".
- **Elementos que pueden impulsarse a pequeña escala**: promoción de la autocorrección de la notación de números del artículo 44 ("몇만/몇백만"). (Los 6 elementos restantes de sustantivos dependientes del artículo 42 tienen sus tablas de verificación completadas en `docs/GRAMMAR_PRECEDENTS_TABLE.md`, pero la implementación real en el código aún no está hecha.)
- **Método de trabajo (obligatorio seguirlo)**: no digas "está hecho" solo mirando el código — ejecuta `main.py correct` con texto real (artículos de noticias, entradas de blog, etc. — los originales con derechos de autor se quedan solo en el scratch pad y no se suben al repositorio) para verificar. Este enfoque ha detectado errores reales varias veces (consulta cada elemento en `docs/IMPLEMENTATION_LOG.md`). Las pruebas de regresión usan `examples/sample.srt` como fixture básico.
- **Convención tras la finalización**: cuando se termina una función: (1) comprobación de regresión con `examples/sample.srt` → (2) sincronizar `PRD.md` y los `docs/*.md` relacionados, más el archivo espejo `C:\Users\user\Documents\자막_맞춤법교정_PRD.md` → (3) git commit. Los mensajes de commit mantienen el estilo de ser específicos sobre el "por qué" y "qué error se corrigió" (consulta git log). **El git commit está automatizado para este proyecto (2026-07-17, instrucción del usuario) — se hace commit automáticamente al completar, sin solicitudes separadas. Sin embargo, git push no está incluido y siempre requiere una aprobación explícita.** (Excepción: la ejecución no supervisada como la tarea programada `gananda-precedent-research` sigue las instrucciones del propio archivo de la tarea (no hacer commits), ya que un humano aún no ha revisado los resultados.)

## 1. Contexto y objetivo

La herramienta existente de corrección automática del coreano, el 'Corrector Ortográfico de la Universidad Nacional de Pusan', tenía cuatro grandes frustraciones: **generaba demasiados falsos positivos (marcaba como errores incluso expresiones normales y nombres propios), exigía correcciones sin ofrecer ningún fundamento de por qué algo estaba mal, las propias sugerencias de corrección eran tan inconsistentes que parecían aleatorias — haciendo que esas sugerencias se sintieran como nuevos errores, y había un límite en la cantidad de caracteres que se podían revisar de una vez, por lo que los documentos largos había que revisarlos dividiéndolos en varias páginas.**

Este proyecto responde directamente a estos cuatro problemas: consulta en tiempo real el Diccionario Estándar del Coreano, Urimalsaem y las normas lingüísticas del Instituto Nacional de la Lengua Coreana para dejar claro el fundamento de sus decisiones (indicando siempre el fundamento en el motivo de la marca), corrige automáticamente solo los elementos con evidencia firme, nunca corrige de forma aleatoria los elementos ambiguos o cuya respuesta depende del contexto sino que los deja a revisión humana, y procesa un archivo de documento entero de una sola vez sin límite de caracteres — de esto, la v1 se centra en la **corrección de espaciado y ortografía**.

**Objetivo**: lograr cero errores en los elementos autocorregidos, basándose en referencias normativas lingüísticas autoritativas y no en conjeturas probabilísticas. Los elementos con evidencia incierta nunca se corrigen a la ligera, sino que se pasan a un humano.

**Usuarios objetivo**: traductores profesionales. El propósito es reducir la carga de su trabajo repetitivo de corrección de espaciado y ortografía. Por eso, tanto los falsos positivos (marcar como incorrecto algo que es normal) como las omisiones (pasar por alto un error real) contradicen este propósito — los falsos positivos hacen que el traductor gaste tiempo de revisión innecesario, y las omisiones dejan intacto el esfuerzo que se pretendía aliviar desde el principio. Por esto, el principio de "procesar automáticamente solo lo seguro, delegar siempre lo ambiguo a un humano" es especialmente importante.

## 2. Alcance (v1)

- Función: **corrección de espaciado entre palabras + corrección de ortografía** de texto coreano
- Destino: documentos coreanos en diversos formatos, como texto plano (.txt), MS Word (.docx) y subtítulos (.srt) — los archivos de subtítulos son solo uno de los formatos admitidos; esta herramienta no es solo para el trabajo con subtítulos
- Idioma objetivo: **exclusivamente coreano**

### Elementos pospuestos a la v2 (fuera de alcance)
- Verificación de la naturalidad/precisión del texto traducido (requiere comparación con el texto original y juicio sobre el estilo de traducción, lo cual no se puede verificar solo con el criterio de esta herramienta de "referencias normativas autoritativas" — consulta `docs/IMPLEMENTATION_LOG.md` §13)

## 3. Entrada / salida

- **Entrada**: archivos de subtítulos (.srt), texto plano (.txt), MS Word (.docx)
- **Salida**:
  - Archivo de resultado corregido (manteniendo el mismo formato que el original — los .srt conservan incluso los códigos de tiempo)
  - Archivo de informe de marcas (lista de elementos demasiado ambiguos para autocorregir)

## 4. Forma de uso y stack tecnológico

- **Herramienta CLI**
- Lenguaje de desarrollo: **Python**
- **Framework CLI: Typer**
  - La estructura requiere al menos 2 subcomandos (`correct`: ejecutar la corrección de texto, `apply-report`: volver a aplicar al original el informe rellenado por el usuario), lo que hace que la gestión de subcomandos sea más fácil que con argparse
  - Basado en type hints, lo cual encaja bien con este proyecto que maneja estructuras de datos claras, como las respuestas de la API del Instituto Nacional de la Lengua Coreana
  - Basado en Click, mantiene la estabilidad a la vez que reduce el código repetitivo
  - Sigue las convenciones para una futura distribución por pip

### Principios de arquitectura (preparación para futuras extensiones)

La lógica de corrección (consulta de diccionario/normas, decisión, generación de marcas) se diseña como un **módulo de biblioteca puro, separado de la CLI**. La CLI (Typer) queda solo como una interfaz ligera que llama a esta biblioteca. Así, en la expansión del backend de §9, el mismo motor de corrección se puede reutilizar tal cual en un servidor de API (sin necesidad de reescribir el código de la CLI). En la etapa de la v1 no se implementa el backend directamente — lo que se está construyendo ahora es, ante todo, una herramienta CLI local.

## 5. Motor de decisión de corrección (diseño central)

Al encontrar una frase ambigua, juzga en el siguiente orden, y si no puede tener certeza hasta el final, **la marca sin autocorregirla, dejándola tal cual** (bajo el principio de que un estado sin corregir es mejor que una corrección incorrecta).

1. **Juicio primario — fundamento normativo/de diccionario**
   - Diccionario Estándar del Coreano, Urimalsaem (Open API del Instituto Nacional de la Lengua Coreana, `search.do`) — comprobar la existencia del lema
   - Distinguir compuestos (notación con guion, con categoría gramatical → siempre juntos) de sintagmas nominales (notación con caret, `pos: "sin categoría gramatical"` → principio de espaciado entre palabras, se permite juntarlos) usando los campos `word`/`pos` de la respuesta de `search.do` del Diccionario Estándar del Coreano. Los compuestos que kiwi.space() pasa por alto (por ejemplo, "노천 카페" → no se corrige) se complementan con la autocorrección basada en el diccionario (`compound_status()`, `correct_compound_spacing()`, implementado)
   - API de contenido del Diccionario Estándar del Coreano (`view.do`) — comprobar ejemplos de uso y el fundamento ortográfico del coreano (`norm_info`) adjunto a algunas palabras (aún no implementado)
   - Open API de normas lingüísticas del coreano (`kornorms/exampleReqList.do`) — consultar los ejemplos de notación de extranjerismos/romanización ya confirmados oficialmente por el Instituto Nacional de la Lengua Coreana (notación en coreano ↔ notación en idioma original, nombres de persona/lugar/términos generales). Requiere una nueva clave de API
   - Texto original de las reglas de notación de extranjerismos (sitio web de normas lingüísticas del Instituto Nacional de la Lengua Coreana, los 5 principios básicos de notación + las reglas detalladas de notación por idioma) — documentos estáticos sin API. Se consulta solo como último recurso al tratar extranjerismos completamente nuevos (neologismos sin notación oficial) que ni siquiera están en la API de kornorms. Si aun así es ambiguo, pasa a la fase 3

2. **Juicio secundario — archivo de respuestas de Online Ganada**
   - Online Ganada no es una API en tiempo real, sino un tablón que responden personas directamente, así que no se hacen consultas en tiempo real
   - En su lugar, se aprovecha únicamente **buscando/consultando el archivo público de respuestas pasadas ya existente** (los precedentes acumulados están en `subtitle_corrector/gananda_precedents.py`, y la gramática de backlog aún no trasladada al código está en `docs/GRAMMAR_PRECEDENTS_TABLE.md`)

3. **Terciario — si aun así es ambiguo → delegar a un humano**
   - Autocorrección prohibida, marcar en el informe

### Principio central: "Los datos del diccionario en tiempo real siempre tienen prioridad"

El resultado consultado en tiempo real a través de la API del Diccionario Estándar del Coreano/Urimalsaem siempre tiene prioridad sobre las suposiciones codificadas de forma fija en el código o el contenido de material educativo aprendido en el pasado. Como las normas y los diccionarios se revisan, no se debe fijar en el código un valor codificado con la idea de "como lo comprobé antes, está bien"; hay que volver a consultar en cada momento en que se necesite una decisión. Por qué este principio fue necesario en la práctica (un caso en el que una suposición codificada de forma fija quedó realmente obsoleta y se convirtió en un error) se puede ver en `docs/IMPLEMENTATION_LOG.md` §17 "Reemplazar suposiciones de verificación codificadas de forma fija por consultas en tiempo real".

### Principio de trabajo: "Primero la tabla de verificación, el código después" (confirmado 2026-07-17)

En el patrón 2 de `correct_aux_verb_spacing()` (tipo "할만하다"), al proceder escribiendo primero el código y parcheando las excepciones a medida que se descubrían, se acabó cometiendo dos veces el mismo error que el usuario señaló con ejemplos de uso reales de Urimalsaem ("할만하다" se corrigió incorrectamente como "할 만 하다"). La causa estaba en el propio orden: escribir primero el código bajo la suposición de "la regla debería ser así" y verificarla después con el diccionario.

**A partir de ahora, al añadir nuevas reglas (especialmente patrones gramaticales que puedan tener excepciones), se debe seguir obligatoriamente este orden** (consulta `.claude/skills/grammar-rule-verify-then-code/SKILL.md` para el procedimiento concreto):
1. Consulta primero directamente por la API del diccionario todos los casos posibles (todas las expresiones que puedan entrar en ese patrón, hasta los precedentes del Diccionario Estándar del Coreano/Urimalsaem/kornorms/Online Ganada como en §5-1/2/3) y **crea una tabla de respuestas (qué entrada → qué respuesta correcta).**
2. Escribe un código que se ajuste exactamente a esa tabla — es el código el que sigue a la tabla, no la tabla la que verifica el código a posteriori.
3. Si tras la implementación se descubre un caso nuevo que no estaba en la tabla, no parchees el código de forma temporal; primero añade ese caso a la tabla (volviendo a consultar el diccionario) y luego corrige el código para que se ajuste a la tabla.

### Limitaciones conocidas / requisitos de mantenimiento

La lista completa de los falsos positivos/errores concretos descubiertos durante el uso real y sus principios de corrección, así como las limitaciones aún no implementadas, se trasladó a `docs/KNOWN_LIMITATIONS.md` — revísala obligatoriamente antes de añadir nuevas funciones.

## 6. Flujo de trabajo de marcado y reaplicación (implementación completa — `correct` / `apply-report`)

1. Procesar el archivo de subtítulos completo
2. Los elementos de los que se puede tener certeza se autocorrigen de inmediato
3. Los elementos ambiguos no interrumpen la ejecución; una vez terminado todo el procesamiento, **se recopilan y se emiten en un único archivo de informe** (número de línea + texto + fundamento de referencia). Para los elementos que, como nombres de persona/lugar, sí se aplicaron automáticamente pero requieren una doble comprobación, se deja en el informe, junto con el texto de resultado ya aplicado, el fundamento de referencia de qué se cambió y por qué.
4. El usuario introduce directamente los valores de corrección en el archivo de informe
5. Al ejecutar el programa de nuevo, los valores de corrección introducidos por el usuario **se reflejan automáticamente en el archivo de subtítulos original**

## 7. Criterios de finalización / método de verificación

- **Método de verificación**: medición de la precisión frente a un conjunto de pruebas al que una persona ha añadido las respuestas correctas
  - Objetivo: cero errores entre los elementos que el programa corrigió automáticamente (sin marcas)
- **Origen del conjunto de pruebas**: recopilado/creado directamente (reuniendo vídeos reales de YouTube/resultados de STT y etiquetando las respuestas correctas)

## 8. Dependencias / trabajos previos

- [x] Solicitud de clave de la Open API del Instituto Nacional de la Lengua Coreana (Diccionario Estándar del Coreano, Urimalsaem)
- [x] Solicitud de clave de la Open API de normas lingüísticas del coreano (kornorms, ejemplos de notación de extranjerismos/romanización)
- [x] Acumulación de precedentes de Online Ganada — implementada investigando por lotes los casos que realmente se usan, en lugar de un rastreo completo (consulta `docs/IMPLEMENTATION_LOG.md` §17)
- [ ] Recopilación del conjunto de pruebas y etiquetado de las respuestas correctas

## 9. Hoja de ruta de futuras extensiones (después de la v1)

Lo que se está construyendo ahora es una herramienta CLI local, pero se dejan los siguientes elementos como hoja de ruta considerando la posibilidad de expandirla más adelante a una forma de servicio (web/backend). En el diseño de la v1 solo se refleja el "principio de arquitectura" de §4 (separación del motor de corrección y la interfaz), sin construir las funciones de abajo en sí.

- **Inicio de sesión/cuentas**: necesario para gestionar el historial de procesamiento por usuario. El método de autenticación (implementación propia vs OAuth, etc.) está por decidir. Aún no implementado — el almacenamiento de §11 funciona sin inicio de sesión al nivel de "cualquiera que conozca el id puede ver ese resultado" (seguridad al nivel de compartir un enlace corto). Para gestionar varios usuarios de forma diferenciada, este elemento debe implementarse primero.
- **Almacenamiento — implementación completa (2026-07-16, consulta §11)**: los resultados de corrección y los informes de marcas de los documentos cargados se guardan en Supabase (Postgres). La política de duración del almacenamiento/tratamiento de información personal (contenido de los documentos) aún no se ha decidido (conservación indefinida por ahora) — debe decidirse obligatoriamente si sale como servicio real.
- **Pago**: si habrá un plan de pago/facturación por uso. Qué funciones se harán de pago (por ejemplo, volumen de procesamiento, número de llamadas a la API de ortografía) está por decidir
- **Diccionarios de terminología especializada por dominio**: corrección de términos especializados de campos concretos (medicina, derecho, etc.) como el diccionario de terminología médica (KMLE). Como son sitios privados y no la Open API oficial del Instituto Nacional de la Lengua Coreana, hay que comprobar primero sus términos de uso, y como se sale del alcance de la v1 de texto coreano general, se pospone para después de la v2
- Cuando esta hoja de ruta se concrete, se tratará en un PRD separado (la arquitectura de backend, la autenticación y la integración de pagos se salen del alcance de este documento)

## 10. TBD (decisiones necesarias más adelante)

- Cronograma de desarrollo / plazo objetivo
- Método de despliegue (paquete pip, etc.)
- Especificación exacta del formato del archivo de informe (json/csv, etc.)
- Objetivos de rendimiento como la velocidad de procesamiento
- Arquitectura detallada de los módulos, política de gestión de errores

## 11. API web / almacenamiento (implementación completa, 2026-07-16)

Como tarea de la asignatura ("añadir un backend a mi servicio"), se implementó realmente el elemento de "almacenamiento" de §9. No se añadió ninguna lógica de corrección nueva; simplemente se llama al motor existente tal cual, según el principio de arquitectura de §4.

- **Composición**: `subtitle_corrector/api.py` (FastAPI) — `POST /api/correct` (carga de `.srt` → `parsers.parse_srt` → `engine.correct_entries` → guardar el resultado) / `GET /api/reports/{id}` (volver a consultar el resultado guardado). `static/index.html` sirve tanto de pantalla de carga como de pantalla de resultados (con `?id=` el resultado se mantiene al recargar y en otros dispositivos).
- **Almacén**: Supabase (Postgres), `subtitle_corrector/store.py` llama directamente a REST (PostgREST) mediante `requests`. El esquema de la tabla está en `supabase_schema.sql`.
- **Diseño de seguridad — la estructura que eligió este proyecto NO es el patrón del material del curso de "el navegador accede directamente a Supabase"**: el navegador solo hace peticiones a este servidor FastAPI y nunca accede directamente a Supabase. Por tanto, es seguro tener la `SUPABASE_SERVICE_KEY` (clave de administrador, ignora la RLS) solo como variable de entorno del lado del servidor, y la tabla `reports` tiene la RLS activada sin crear ninguna política, de modo que la clave anon (pública) rechaza cualquier petición — el servidor es la única vía de acceso.
- **Valores secretos**: `STDICT_API_KEY`/`OPENDICT_API_KEY`/`KORNORMS_API_KEY` (existentes) + `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` (nuevos), todos existen únicamente en `.env` (local) / variables de entorno de Render (despliegue). Consulta `.env.example`.
- **Despliegue**: se intentó desplegar FastAPI tal cual en Render (servicio web gratuito). La creación de la cuenta y la configuración del panel las debe hacer el usuario directamente (la IA no puede iniciar sesión en su lugar), así que se recopilaron los pasos en `DEPLOY.md`. **Resultado del intento de despliegue real del 2026-07-22: el uso de memoria del modelo de kiwipiepy (unos 310MB) llena casi por completo el límite de 512MB del nivel gratuito de Render y provoca errores 502 — se pospuso este intento de despliegue en sí** (consulta `docs/RETROSPECTIVE.md`). Las pruebas locales (verificación de la integración del motor con un almacén de stub) y la integración real con Supabase (2026-07-16, el usuario creó la cuenta directamente) sí se completaron.
- **Pruebas**: se comprobaron las rutas de FastAPI (200/404, validación del formato de archivo) y la integración del motor con `examples/sample.srt` (sustituyendo `store.save_report`/`get_report` por stubs para verificar sin una cuenta real de Supabase).
- **4 errores de uso real relacionados con la API web/almacenamiento, falsos positivos por palabras no registradas en kiwi, revisión integral de seguridad/SQL, aislamiento de fallos de guardado, etc.**: para el historial detallado, consulta `docs/IMPLEMENTATION_LOG.md` (elementos relacionados con §11, §13, §24, §25).

> 🤖 Traducido automáticamente del [original en coreano](./PRD.md); aún no revisado por un hablante nativo.
