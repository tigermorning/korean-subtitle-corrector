<!-- 관리: 마지막 점검 2026-11-20. 옛 AGENTS.md·CLAUDE.md 원문은 docs/AGENT_RULES_BACKGROUND.md -->
# 한국어 자막 교정기

## 무엇인가
- 자막을 권위 있는 규범(표준국어대사전·우리말샘·어문 규범)을 근거로 교정한다. 애매하면 자동으로 고치지 않고 사람에게 묻는다. 이 원칙과 부딪히는 자동화는 제안하지 않는다

## 확인 명령
- 고친 뒤 돌린다(2026-11-20 돌려 봄, 파이썬은 `.venv/Scripts/python.exe`)
  - 공개 계약: `python tools/check_public_api.py` → `공개 계약 4개 확인, 어긋난 것 0건`
  - 미해석 이름: `python tools/check_names.py` → `… 미해석 전역 이름 0건`
  - 전체 시험: `pytest` → `768 passed`(약 32분, 오래 걸리니 백그라운드로). 사전 API를 실시간으로 부른다(네트워크·`.env` 키 필요). 실패하면 코드 회귀인지 사전 개정인지부터 가린다
- 구조를 바꾼 뒤(모듈 분할·함수 이동): `python tools/diff_behavior.py` → 순수 이동이면 SHA256까지 같다
- 평가셋 `examples/eval/heldout.jsonl`(41건)에 보태기 전: `python tools/verify_eval_labels.py --file <쌍 목록>`으로 라벨부터 검증한다
- 자동 교정 규칙을 넣거나 고치기 전: `python tools/audit_auto_rules.py`로 근거의 극성을 본다. 새 규칙은 그 파일 `RULES` 표에 한 줄 더한다

## 먼저 물을 것
- 공개 계약(`docs/PUBLIC_API.md`, `tools/check_public_api.py`의 `CONTRACT`)을 바꾸는 일. 다른 도구가 이 저장소를 import해서 쓴다
- 배포용 `requirements.txt`에 의존성을 더하는 일(메모리 한계)

## 건드리면 안 되는 것
- 커밋 전 검사(공개 계약·미해석 이름)를 건너뛰지 않는다 — 막힘: `tools/hooks/pre-commit`
  - 새 클론·워크트리에서는 `.git/hooks/pre-commit`에 `tools/hooks/pre-commit`으로 넘기는 shim을 둔다. `git config core.hooksPath tools/hooks`는 쓰지 않는다(전역 gitleaks 훅이 꺼진다, 2026-11-20 확인)
- 유사 판례 검색(`precedent_search.py`)을 교정 판정 경로(`word_exists`, `check_precedent`)에 잇지 않는다. 임베딩 유사도는 규범 근거가 아니다 — 글로만
- 사투리: 지정 없는 화자는 표준어로 보고, 표준이 아닌 어미도 자동 교정하지 않는다. 사투리 화자도 플래그만 남긴다. `to_standard` 모드도 텍스트를 바꾸지 않는다(2026-08-03) — 글로만

## 코드만 봐서는 모르는 것
- 실패를 성공처럼 흡수하지 않는다: «못 물어봤다»와 «물어봤더니 없다»를 한 값으로 돌려주면 장애가 판정으로 둔갑한다. 흡수하면 `note_lookup_failure()`·`AppliedNote`·`lookup_failed`로 위에 올린다. 다섯 번 반복된 사고(DESIGN_PRINCIPLES 원리 5, 2026-09-02)
- 사전 API 호출에는 `dictionary/clients.py`의 `_HEADERS`를 싣는다. 빠지면 어문 규범 API가 403을 주고 외래어 교정이 «등재된 표기 없음»으로 조용히 죽는다. 브라우저를 흉내 내지 않는다(2026-09-01)
- `search_dialect()`는 실패와 매칭 없음이 둘 다 `[]`다(의도된 설계). 상태는 `lookup_stats()`나 원 요청으로 본다. 지역어 API는 2026-09-02에도 서버 500
- 자동 교정 로그는 문자열이 아니라 `report.AppliedNote` 목록이다. `"[12] …"` 문자열을 다시 파싱하지 않고, 새 로그의 `is_edit`를 맞게 넣는다(틀리면 되돌리기에서 빠짐, 2026-08-04)
- 긍정 근거(«붙임형이 사전에 있다»)만으로 원문을 바꾸는 규칙은 뜻을 바꾼다: `집 개`→`집개`, `250cc 정도`→`정도되다`(2026-08-04)
- 엔진 규칙은 `engine/`의 규칙 모듈에 넣고 `pipeline.py`에는 호출 순서만 둔다. `Kiwi()`는 `kiwi_adapter.py`에만 둔다. 새 공개 함수는 `engine/__init__.py`의 `__all__`에 더한다(2026-08-02)
- 사전 조회: 요청은 `clients.py`, 응답으로 내리는 결론은 `headwords.py`·`terms.py`. 섞지 않는다(2026-08-02)
- 사투리 표에 항목을 넣을 때는 우리말샘 방언 표제어(뜻풀이 `'X'의 방언`)로 확인하고 근거 주석을 함께 적는다
- 문서의 `§31` 같은 번호는 구현 이력 절 번호다. §31~§95는 `docs/log-archive/2026-h2.md`, §96부터 `docs/IMPLEMENTATION_LOG.md`

## 더 읽을 곳
- `docs/BACKLOG.md` — 세션을 시작하면 먼저 읽고 사용자에게 보고한다(2026-07-27 사용자 지시). 우선순위·착수 순서는 이 파일만 기준이다. 새로 미루는 일은 여기에 더한다
- `PRD.md` 맨 위 «문서 구성»·«세션 인계 노트» — 작업을 시작하기 전에
- `docs/DESIGN_PRINCIPLES.md` — 오탐지·과교정 리포트를 받으면 먼저
- `docs/ISSUES_SUMMARY.md` — «이 버그 전에도 있었나?» 같은 전체 색인
- `docs/AGENT_RULES_BACKGROUND.md` — 위 규칙의 배경·계기 원문
