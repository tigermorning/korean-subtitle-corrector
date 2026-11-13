"""시험은 사전 응답 디스크 캐시를 쓰지 않는다 — 가짜 응답을 넣는 시험이 디스크의 진짜 응답을 읽으면 안 된다.
.env보다 먼저 빈 값을 넣는다(load_dotenv는 이미 있는 값을 덮지 않는다)."""
import os

os.environ["DICT_CACHE_DIR"] = ""
# 내려받은 사전 색인(로컬 조회)도 끈다 — 시험은 가짜 응답·가짜 색인만 쓴다.
os.environ["DICT_LOCAL_DIR"] = ""
