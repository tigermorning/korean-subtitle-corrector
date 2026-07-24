<!-- lang-switcher:start -->
<p align="center">
  <a href="PRD.md">한국어</a>
  ·
  English
  ·
  <a href="PRD.zh-CN.md">中文(简体)</a>
  ·
  <a href="PRD.zh-TW.md">中文(繁體)</a>
  ·
  <a href="PRD.ja.md">日本語</a>
  ·
  <a href="PRD.es.md">Español</a>
  ·
  <a href="PRD.ar.md">العربية</a>
</p>
<!-- lang-switcher:end -->

# Korean Spacing & Spelling Auto-Correction CLI Tool — PRD (Draft)

## Document Structure (2026-07-24 Modularization)

This PRD has grown too large (nearly 400 lines), so it was split as follows. This file now contains only the **core specifications that rarely change**, while the practical usage logs, limitations lists, and verification tables that accumulate over time have been moved to separate files.

- **`PRD.md` (this file)**: Background/Purpose, Scope, Input/Output, Tech Stack, Core Design of the Correction Judgment Engine, Workflow, Completion Criteria, Dependencies, Roadmap, TBD.
- **`docs/KNOWN_LIMITATIONS.md`**: Separated from §5. A list of false positives/bugs discovered during actual use and their correction principles, as well as unimplemented limitations recorded by case (former §5 "Known Limitations / Maintenance Requirements").
- **`docs/IMPLEMENTATION_LOG.md`**: Former §13–§27. A log recording bugs discovered during actual text proofreading and their correction history in chronological order. If the file grows too large again, the file specifies rules for semi-annual archiving.
- **`docs/GRAMMAR_PRECEDENTS_TABLE.md`**: Former §18. A verification table of grammar rules not yet implemented in code, pre-researched through Online Gananda.
- **`subtitle_corrector/gananda_precedents.py`**: Precedents from Online Gananda for expressions already handled by the code (should be kept alongside the code).

New sessions are recommended to read through the four files above in order after this file. Since automation (skills/scheduled tasks) references these exact paths, if this structure is changed, the following list must also be updated: 4 skills in `.claude/skills/`, `~/.claude/scheduled-tasks/gananda-precedent-research/SKILL.md`, `AGENTS.md`, and the mirror file `C:\Users\user\Documents\자막_맞춤법교정_PRD.md`.

## Session Handoff Notes (Read this first when continuing with another AI coding tool)

- **Core Principle**: "Based on authoritative normative references, not probabilistic guesses — when in doubt, always ask the user for confirmation." Do not even suggest automation that violates this principle (e.g., judging based on context inference). The entire list in `docs/KNOWN_LIMITATIONS.md` is a record of bugs and design decisions discovered/corrected while trying to uphold this principle, so review it before adding new features.
- **What has been implemented so far**: Foreign word notation (kornorms, auto-correction of general terms / proper nouns always flagged for confirmation), spelling (Standard Korean Dictionary + Urimalsaem, checking only NNG/VV/VA), spacing (particle/ending combinations auto-corrected, compounds/dependent nouns/auxiliary verbs auto-corrected when dictionary evidence exists otherwise flagged, auxiliary verb spacing unified per rules), confirmed error patterns/discriminatory expression auto-correction, purified expression flags. For details and the discovery history of each bug, see `docs/KNOWN_LIMITATIONS.md` and `docs/IMPLEMENTATION_LOG.md`. **Web API + Storage (§11, implemented 2026-07-16)**: `subtitle_corrector/api.py` (FastAPI) reuses the same engine (`engine.correct_entries`) as the CLI for `.srt`/`.txt`/`.docx` upload → correction results saved to Supabase, `static/index.html` serves as both upload and result display screen (with proper noun/cuisine name input fields). Local testing completed; actual Supabase/Render deployment requires the user to follow `DEPLOY.md` manually (AI cannot create accounts). **2026-07-22 Render deployment attempt: kiwipiepy model loading alone consumes about 310MB, nearly filling the free tier 512MB limit, causing 502 errors — deployment has been put on hold** (see `docs/RETROSPECTIVE.md`). The next session should first confirm whether to retry deployment. See `docs/IMPLEMENTATION_LOG.md` §13: the problem of kiwi incorrectly splitting unknown words (proper nouns, cuisine names) was resolved with `register_custom_words()` (kiwi.add_user_word).
- **Largest remaining task**: **Online Gananda integration (Phase 2, unimplemented)** — A feature to supplement ambiguous notations that cannot be resolved even with dictionary/normative references (Phase 1) using the National Institute of the Korean Language's Online Gananda archive of past answers. Since it's a Q&A board without a clean API, the search/crawl method needs to be researched first, and the scope is quite large (see §8 dependency checklist).
- **Immediate next task (pending start, saved 2026-07-21)**: Investigation/implementation of "noun+드리다" false positives (e.g., 부탁드리다) in `docs/IMPLEMENTATION_LOG.md` §27 — not yet started, postponed considering token consumption, to be done upon user request. To continue this task in the next session, read §27 in its entirety first.
- **See `docs/KNOWN_LIMITATIONS.md`**: Three severe false positives discovered during actual use (discriminatory expression replacement incorrectly affecting unrelated words, auxiliary verb spacing forcibly splitting compound verbs registered in the dictionary, kiwi's "요" false tagging) have all been fixed at the pattern level. Be careful not to introduce similar "replacing based on characters alone" or "enforcing rules without dictionary verification" types of bugs in the future.
- **Small-scale items that can be pushed forward**: Promotion of §44 number notation ("몇만/몇백만") auto-correction. (§42 dependent noun remaining 6 items have verification tables completed in `docs/GRAMMAR_PRECEDENTS_TABLE.md`, but actual code implementation is not yet done.)
- **Work method (must follow)**: Don't just look at code and say "it's done" — run `main.py correct` with actual text (news articles, blog posts, etc. — copyrighted originals stay only in the scratch pad and are not committed to the repo) to verify. This approach has caught actual bugs multiple times (see each item in `docs/IMPLEMENTATION_LOG.md`). Regression testing uses `examples/sample.srt` as the basic fixture.
- **Post-completion convention**: When a feature is finished: (1) regression check with `examples/sample.srt` → (2) sync `PRD.md` and related `docs/*.md`, plus the mirror file `C:\Users\user\Documents\자막_맞춤법교정_PRD.md` → (3) git commit. Commit messages maintain the style of being specific about "why" and "what bug was fixed" (see git log). **Git commit is automated for this project (2026-07-17, user instruction) — commit automatically when complete without separate requests. However, git push is not included and always requires explicit approval.** (Exception: unmanned execution like the `gananda-precedent-research` scheduled task follows the task file's own instructions (no commits) since a human hasn't reviewed the results yet.)

## 1. Background and Purpose

The existing Korean auto-correction tool 'Pusan National University Spelling Checker' had four major frustrations: **excessive false positives (incorrectly flagging normal expressions and proper nouns as errors), demanding corrections without providing any basis for why something was wrong, the correction suggestions themselves appearing inconsistent and random — making them feel like new errors, and character limits preventing checking of long documents in a single pass.**

This project directly addresses these four problems: real-time querying of the National Institute of the Korean Language's Standard Korean Dictionary, Urimalsaem, and language norms to clearly document the basis for judgments (always specifying the basis in flag reasons), automatically correcting only items with firm evidence, leaving ambiguous items or those that depend on context to human review rather than randomly correcting them, and uploading entire document files without character limits for one-pass processing — of which v1 focuses on **spacing and spelling correction**.

**Goal**: Achieve zero errors in auto-corrected items based on authoritative language normative references, not probabilistic guesses. Never casually correct items with uncertain evidence — pass them to humans.

**Target users**: Professional translators. The purpose is to reduce the burden of their repetitive spacing and spelling correction work. Both false positives (flagging correct text as wrong) and omissions (missing real errors) contradict this purpose — false positives waste translators' time on unnecessary proofreading, while omissions leave the very effort the tool was meant to alleviate. This is why the principle of "auto-process only what's certain, always delegate ambiguity to humans" is especially important.

## 2. Scope (v1)

- **Features**: Spacing correction + spelling correction for Korean text
- **Targets**: Korean documents in various formats — plain text (.txt), MS Word (.docx), subtitles (.srt). Subtitle files are just one supported format; this tool is not exclusively for subtitle work.
- **Target language**: **Korean only**

### Items postponed to v2 (Out of scope)
- Verification of naturalness/accuracy of translated text (requires original text comparison/translation style judgment, which cannot be verified with this tool's criterion of "authoritative normative references" — see `docs/IMPLEMENTATION_LOG.md` §13)

## 3. Input / Output

- **Input**: Subtitle (.srt), plain text (.txt), MS Word (.docx) files
- **Output**:
  - Corrected result file (maintaining the same format as the original — .srt preserves even timecodes)
  - Flag report file (list of items too ambiguous to auto-correct)

## 4. Usage Form and Tech Stack

- **CLI tool**
- **Development language**: **Python**
- **CLI framework: Typer**
  - The structure requires at least 2 subcommands (`correct`: run text correction, `apply-report`: re-apply user-filled reports to the original), making subcommand management easier than argparse
  - Type hint-based, which pairs well with this project's handling of clear data structures like National Institute of the Korean Language API responses
  - Click-based, maintaining stability while reducing boilerplate
  - Follows conventions for future pip distribution

### Architecture Principles (Future Extension Consideration)

The correction logic (dictionary/normative lookup, judgment, flag generation) is designed as a **pure library module separate from the CLI**. The CLI (Typer) serves only as a thin interface calling this library. This allows the same correction engine to be reused on an API server during §9's backend expansion (without rewriting CLI code). No backend is implemented at the v1 stage — what we're building is strictly a local CLI tool.

## 5. Correction Judgment Engine (Core Design)

When encountering an ambiguous sentence, it judges in the following order, and if it cannot be confident to the end, it **flags without auto-correcting** (the principle that an uncorrected state is better than an incorrect correction).

1. **Primary Judgment — Normative/Dictionary Basis**
   - Standard Korean Dictionary, Urimalsaem (National Institute of the Korean Language Open API, `search.do`) — Check existence of headword
   - Distinguish compound words (hyphenated notation, has POS → always joined) from noun phrases (caret notation, `pos: "no POS"` → spacing principles/joined allowed) using `word`/`pos` fields from Standard Korean Dictionary `search.do` response. Compounds missed by kiwi.space() (e.g., "노천 카페" → not corrected) are supplemented with dictionary-based auto-correction (`compound_status()`, `correct_compound_spacing()`, implemented)
   - Standard Korean Dictionary content API (`view.do`) — Check usage examples, Korean spelling basis (`norm_info`) attached to some words (not yet implemented)
   - Korean Language Norms Open API (`kornorms/exampleReqList.do`) — Query officially confirmed foreign word/romanization notation examples (Korean notation ↔ original notation, personal names/place names/general terms). New API key required
   - Original text of foreign word notation rules (National Institute of the Korean Language Norms website, 5 basic notation principles + language-specific notation details) — Static documents without API. Referenced only as a last resort when dealing with completely new foreign words (neologisms without official notation) not in the kornorms API. If still ambiguous, pass to Phase 3

2. **Secondary Judgment — Online Gananda Answer Archive**
   - Online Gananda is a Q&A board with human responders, not a real-time API, so real-time queries are not made
   - Instead, it is utilized only by **searching/referencing existing public archives of past answers** (accumulated precedents are in `subtitle_corrector/gananda_precedents.py`, backlogged grammar not yet converted to code is in `docs/GRAMMAR_PRECEDENTS_TABLE.md`)

3. **Tertiary — Still Ambiguous → Delegate to Human**
   - Auto-correction prohibited, flag in report

### Core Principle: "Real-time dictionary data always takes precedence"

Results from real-time Standard Korean Dictionary/Urimalsaem API queries always take precedence over hardcoded assumptions in code or previously learned educational material content. Regulations and dictionaries are revised, so don't fix outdated assumptions as hardcoded values in code — re-query whenever judgment is needed. Why this principle is necessary in practice (a case where a hardcoded assumption actually became outdated and caused a bug) can be found in `docs/IMPLEMENTATION_LOG.md` §17 "Replacing hardcoded verification assumptions with real-time queries."

### Work Principle: "Verification table first, code later" (Confirmed 2026-07-17)

When working on `correct_aux_verb_spacing()` pattern 2 ("할만하다" type), the approach of first writing code and patching exceptions as they were discovered resulted in the same error being pointed out twice by the user with actual Urimalsaem usage examples ("할만하다" was incorrectly changed to "할 만 하다"). The cause was in the order itself — writing code first based on the assumption "the rule should be like this" and then verifying against the dictionary.

**When adding new rules (especially grammar patterns that may have exceptions) in the future, this order must be followed** (see `.claude/skills/grammar-rule-verify-then-code/SKILL.md` for specific procedures):
1. Query all possible cases (all expressions that could fit the pattern, up to §5-1/2/3 Standard Korean Dictionary/Urimalsaem/kornorms/Online Gananda precedents) directly via dictionary APIs to create a **verification table (what input → what correct answer)**.
2. Write code that exactly matches the table — the code follows the table, not the table retroactively verifying the code.
3. If new cases not in the table are found after implementation, don't temporarily patch the code — first add the case to the table (re-query dictionary), then fix the code to match the table.

### Known Limitations / Maintenance Requirements

The complete list of specific false positives/bugs discovered during actual use and their correction principles, as well as unimplemented limitations, has been moved to `docs/KNOWN_LIMITATIONS.md` — review it before adding new features.

## 6. Flag & Re-application Workflow (Implemented — `correct` / `apply-report`)

1. Process the entire subtitle file
2. Immediately auto-correct items with firm confidence
3. Ambiguous items are not interrupted during execution; after all processing is complete, they are **collected and output in a single report file** (line number + text + reference basis). For items like personal names/place names that were auto-applied but need double-checking, the report includes what was changed and why alongside the already-applied result text.
4. User enters correction values directly into the report file
5. When the program is run again, the user's input values are **automatically applied to the original subtitle file**

## 7. Completion Criteria / Verification Method

- **Verification method**: Measuring accuracy against a test set with human-labeled correct answers
  - Goal: Zero errors in items auto-corrected (without flags) by the program
- **Test set source**: Directly collected/created (gathering actual YouTube videos/STT outputs and labeling correct answers)

## 8. Dependencies / Prerequisites

- [x] National Institute of the Korean Language Open API key application (Standard Korean Dictionary, Urimalsaem)
- [x] Korean Language Norms Open API key application (kornorms, foreign word/romanization notation examples)
- [x] Online Gananda precedent accumulation — Implemented by investigating actually-used cases in batches rather than full crawling (see `docs/IMPLEMENTATION_LOG.md` §17)
- [ ] Test set collection and correct answer labeling

## 9. Future Extension Roadmap (After v1)

What we're building now is a local CLI tool, but the following items are left as a roadmap considering the possibility of future expansion to a service form (web/backend). The v1 design only reflects §4's "Architecture Principles" (separation of correction engine and interface), not the features below.

- **Login/Account**: Required for managing per-user processing history. Authentication method (self-implementation vs OAuth etc.) is undetermined. Not yet implemented — §11's storage works without login at the level of "anyone who knows the ID can view the result" (short link sharing level security). This must be implemented before managing multiple users separately.
- **Storage — Implemented (2026-07-16, see §11)**: Correction results and flag reports for uploaded documents are stored in Supabase (Postgres). Storage duration/personal information (document content) handling policy has not been determined yet (currently indefinite) — must be decided when moving to actual service.
- **Payment**: Paid plan/usage-based billing. Which features to monetize (e.g., processing volume, spelling API call count) is undetermined.
- **Domain-specific terminology dictionaries**: Correction of specialized terms in specific fields (medicine, law, etc.) such as medical terminology dictionary (KMLE). Since these are private sites rather than the National Institute of the Korean Language's official Open API, terms of use must be checked first, and it falls outside v1's scope of general Korean text, so postponed to after v2.
- When this roadmap is concretized, it will be separated into a separate PRD (backend architecture, authentication, payment integration are outside this document's scope).

## 10. TBD (Decisions Needed for Later)

- Development schedule / target period
- Deployment method (pip package, etc.)
- Exact format spec for report files (json/csv, etc.)
- Performance targets such as processing speed
- Detailed module architecture, error handling policy

## 11. Web API / Storage (Implemented, 2026-07-16)

As a class assignment ("Adding a backend to my service"), §9's "Storage" item was actually implemented. No new correction logic was added; the existing engine is called directly following §4's architecture principles.

- **Composition**: `subtitle_corrector/api.py` (FastAPI) — `POST /api/correct` (.srt upload → `parsers.parse_srt` → `engine.correct_entries` → save results) / `GET /api/reports/{id}` (retrieve saved results). `static/index.html` serves as both upload and result display screen (`?id=` for refresh/results maintained on other devices).
- **Storage**: Supabase (Postgres), `subtitle_corrector/store.py` directly calls REST (PostgREST) via `requests`. Table schema is in `supabase_schema.sql`.
- **Security Design — This project does NOT use the "browser accesses Supabase directly" pattern from the lecture materials**: The browser only requests this FastAPI server and never directly accesses Supabase. Therefore, it's safe to hold only `SUPABASE_SERVICE_KEY` (admin key, ignores RLS) as a server-side environment variable, and the `reports` table has RLS enabled with no policies created, so the anon (public) key rejects all requests — the server is the only access path.
- **Secrets**: `STDICT_API_KEY`/`OPENDICT_API_KEY`/`KORNORMS_API_KEY` (existing) + `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` (new), all only exist in `.env` (local) / Render environment variables (deployment). See `.env.example`.
- **Deployment**: Attempted deploying FastAPI as-is to Render (free web service). Account creation/dashboard setup must be done by the user (AI cannot log in), so step-by-step instructions are in `DEPLOY.md`. **2026-07-22 actual deployment attempt: kiwipiepy model memory usage (about 310MB) nearly fills the free tier 512MB limit, causing 502 errors — this deployment attempt has been put on hold** (see `docs/RETROSPECTIVE.md`). Local testing (engine integration verification with stub storage) and actual Supabase integration (2026-07-16, user created account) are complete.
- **Testing**: FastAPI routes (200/404, file format validation) and engine integration were verified with `examples/sample.srt` (`store.save_report`/`get_report` replaced with stubs for verification without actual Supabase account).
- **Web API/Storage-related real-world bugs (4 cases), kiwi unregistered word false positives, security/SQL comprehensive review, storage failure isolation, etc.**: For detailed history, see `docs/IMPLEMENTATION_LOG.md` (§11-related items, §13, §24, §25).