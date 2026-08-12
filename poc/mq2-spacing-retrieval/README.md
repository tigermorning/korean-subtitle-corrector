# 문맥 의존 띄어쓰기에 근거 검색을 쓸 수 있는가

**Main Quest 2 — 내 도메인에서 AI로 개선 지점 찾아 PoC 만들기**

한국어 자막 교정기(`korean-subtitle-corrector`)에서 **한글 맞춤법 제42항 이중 기능
단어**의 띄어쓰기 판정에, 축적된 국립국어원 근거를 **검색해서** 쓸 수 있는지 실험했다.

> **결론부터: 가설은 기각됐다.** 문장 임베딩 검색은 비신경 낱말 겹침보다 못했고,
> 이미 맞는 문장을 망가뜨린 유일한 방법이었다. 다만 **병목은 실재했고**, AI를 쓰지
> 않는 하이브리드로 정확도가 73.9% → 89.1%로 올랐다.

## 문서

| 파일 | 내용 |
|---|---|
| [`PROBLEM.md`](PROBLEM.md) | 문제 정의서 — 도메인, 현재 문제, 개선 가설, 대상 사용자, **실행 전 확정한 성공 기준** |
| [`RESULTS.md`](RESULTS.md) | 검증 결과 — 정량 비교, 실패 사례, 모델·라이선스 비교, 최종 결론 |
| `dataset.jsonl` | 평가셋 46건. 라벨은 국립국어원 근거에서 옮겼다 |
| `arms.py` | 비교 대상 5종 구현 |
| `run_poc.py` | 실행기 겸 채점기 |
| `survey.py` | 착수 전 조사 — 실제 데이터에 사례가 몇 건인가 |
| [`comparison.md`](comparison.md) | **큐별 대조표(정성 자료)** — 같은 문장에 arm마다 무엇을 냈는지, 오답은 어떤 근거를 골라서 틀렸는지 |
| `make_comparison.py` | 위 표 생성기 |
| [`demo_output.txt`](demo_output.txt) | **시연 자료** — 실행 화면 그대로 |
| `results*.json` | 원자료. 큐별 입력·출력·근거·정오가 전부 남는다 |

## 무엇을 물었나

한글 맞춤법 제42항은 여덟 낱말(`들·뿐·대로·만큼·만·지·차·판`)이 두 문법 기능을
오간다고 규정한다. 같은 글자인데 앞말과 뜻에 따라 붙이기도 띄기도 한다.

    붙임: 너뿐이다 (조사)         띄움: 웃을 뿐이다 (의존명사)
    붙임: 인사차 들렀다 (접미사)   띄움: 입사 3년 차 (의존명사)
    붙임: 한판 잔치 (합성명사)     띄움: 한 판 더 하자 (수관형사+의존명사)

**사전 조회로는 안 갈린다.** `한판`도 표제어이고 `한 판`도 맞는 표기다.

이 저장소에는 국립국어원 온라인가나다 판례가 축적돼 있는데(`gananda_precedents.py`),
쓰는 방법이 **정확 문자열 일치뿐**이라 판례에 없는 새 문장에서는 근거가 하나도
동원되지 않는다. 임베딩 검색 장치(`precedent_search.py`)도 이미 있지만 그 파일이
"교정 판정에는 절대 쓰지 않는다"고 못박고 있다.

> **이 PoC가 물은 것: 그 금지를 풀어도 되는가?**

## 비교 대상

| arm | 방법 | AI |
|---|---|---|
| B0 | 현재 시스템 전체 (규칙 + 사전 + kiwi) — **기준선** | — |
| B1 | 축적 판례 정확 문자열 일치 — 지금의 검색 방식 | — |
| B2a | 근거 검색 — 낱말 겹침 (비신경 대조군) | — |
| B2b | 근거 검색 — 문장 임베딩 | ✔ |
| B3 | 근거 선택 — 로컬 LLM | ✔ |

모든 arm이 **같은 지식베이스**에서 고른다. 모델이 정답을 만들지 않고, 어느 근거가
이 문장에 해당하는지만 고른다. 판정은 그 근거가 한다.

## 결과

| arm | 정확도 | 오답률 | 과잉교정 | 소요 |
|---|---|---|---|---|
| B0 현재 시스템 | 73.9% | **0.0%** | 1 | 134.7초 |
| B1 정확 일치 | 21.7% | 0.0% | 0 | 0.0초 |
| **B2a 낱말 겹침** | **82.6%** | 17.4% | 2 | **0.1초** |
| B2b 임베딩 | 73.9% | **26.1%** | **4** | 66.7초 |
| B3 LLM (EXAONE) | **89.1%** | 10.9% | 1 | 15.0초 |
| B3 LLM (Qwen2.5) | 76.1% | 23.9% | 2 | 37.7초 |

**사전 확정 기준: S1 실패, S2 실패, S3 통과 → 통합하지 않는다.**

핵심 발견:

1. **임베딩이 비신경 방법보다 나쁘다.** 판정 조건이 "관형사형 어미 뒤" 같은 **형태**를
   말하는데 임베딩은 **의미**를 잰다. 사진 검색은 의미가 곧 답이지만 띄어쓰기는 아니다.
2. **대조군(이미 맞는 문장)을 망가뜨린 arm은 임베딩뿐이다.** `너뿐이야` → `너 뿐이야`.
3. **상업적으로 쓸 수 있는 AI는 전부 비신경 방법에 졌다.** 1등 EXAONE은 라이선스가 막는다.
4. **하이브리드가 답이다.** B0가 기권한 자리에서만 낱말 겹침을 쓰면 73.9% → **89.1%**.
   신경망 없이, 0.1초에.

## 실행 방법

### 준비

```powershell
git clone https://github.com/tigermorning/korean-subtitle-corrector.git
cd korean-subtitle-corrector
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

`.env`에 국립국어원 오픈 API 키를 채운다(무료 발급). **B0(기준선)가 실시간 조회를
하므로 없으면 기준선을 잴 수 없다.**

- `STDICT_API_KEY` 표준국어대사전
- `OPENDICT_API_KEY` 우리말샘
- `KORNORMS_API_KEY` 어문규범

### AI를 쓰지 않는 arm만 (준비물 없음, 3분)

```powershell
.venv\Scripts\python.exe poc\mq2-spacing-retrieval\run_poc.py --arms B0 B1 B2a
```

### 임베딩 arm 포함 (모델 약 500MB 자동 내려받기)

```powershell
.venv\Scripts\pip install -r requirements-optional.txt
.venv\Scripts\python.exe poc\mq2-spacing-retrieval\run_poc.py
```

### LLM arm (Ollama 필요)

```powershell
winget install Ollama.Ollama
ollama pull exaone3.5:7.8b
.venv\Scripts\python.exe poc\mq2-spacing-retrieval\run_poc.py --arms B3
.venv\Scripts\python.exe poc\mq2-spacing-retrieval\run_poc.py --arms B3 --llm-model qwen2.5:7b-instruct
```

WSL에서 돌릴 때 Windows 쪽 Ollama는 HTTP로 닿지 않는다(127.0.0.1 전용). `ollama`
실행 파일을 찾으면 명령 호출로 자동 전환하므로 별도 설정이 필요 없다. **포트를 열지
않는다** — 미공개 원고를 다루는 자리라서다.

### 착수 전 조사 재현

```powershell
.venv\Scripts\python.exe poc\mq2-spacing-retrieval\survey.py
```

## 재현성

- **같은 입력 → 같은 출력** (B3 제외). B0·B1·B2a·B2b는 결정적이다.
  실제로 전체를 두 번 돌려 확인했다 — 정확도·정답 수·오답 수·과잉교정 수가 전부
  같았다(`results.json` vs `results_verify.json`). 소요 시간만 달라진다(사전 API 캐시).
- B3만 확률적이다(`temperature=0`이어도 모델 버전에 흔들린다). 그래서 **결론 근거로
  쓰지 않았다.**
- 모든 중간 결과가 `results*.json`에 남는다 — 입력, arm별 출력, 고른 근거, 정오.
- B0는 국립국어원 API를 실시간 조회하므로 **규정이 개정되면 값이 달라질 수 있다.**
  이 프로젝트가 로컬 사전 복제 대신 API에 의존하기로 한 결정의 결과이며, 실행일
  (2026-08-12)을 함께 봐야 한다.

## 데이터 출처와 라벨

라벨을 직접 정하지 않았다. 전부 저장소에 이미 검증돼 있던 것을 옮겼다.

| 출처 | 건수 |
|---|---|
| `docs/GRAMMAR_PRECEDENTS_TABLE.md` (온라인가나다 답변, qna_seq 명시) | 20 |
| `tests/test_dependent_nouns.py` (기존 정답표 회귀 테스트) | 18 |
| `docs/KNOWN_LIMITATIONS.md` | 5 |
| `subtitle-editor/.tmp/out-large.srt` (실제 Whisper STT 출력) | 3 |

대조군 5건(이미 맞는 문장)을 넣어 **과잉교정**을 측정했다.

## 프라이버시·라이선스·환경

| 항목 | |
|---|---|
| 데이터 전송 | 전부 로컬 + 국립국어원 공식 API. 외부 LLM에 원고를 보내지 않는다 |
| 임베딩 모델 | `paraphrase-multilingual-MiniLM-L12-v2` — Apache 2.0 |
| LLM | `exaone3.5:7.8b` — EXAONE AI Model License **(상업 제약)** / `qwen2.5:7b-instruct` — Apache 2.0 |
| 실행 환경 | 로컬 CPU. GPU 불필요 |
| 비용 | 0 |
| 메모리 주의 | 임베딩 모델 약 500MB. 이 저장소의 웹 배포(무료 티어 512MB)에는 **넣지 않는다** |

## 다음 단계

1. **하이브리드를 제안(플래그)으로만** 붙인다. 자동 적용하지 않는다 — 과잉교정이
   1건에서 3건으로 늘기 때문이다.
2. `차(車)`/`차(茶)`처럼 표면으로 안 갈리는 자리는 검색으로 못 푼다. 백로그 2안
   (오프라인 빈도표)이나 사전의 문형(격틀) 정보가 다음 후보다.
3. 평가셋을 46건에서 늘린다. 지금 결론은 이 46건에 한한다.
