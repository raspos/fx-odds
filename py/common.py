"""공통 경로·환경 로딩·보안 유틸. API 키는 출력하지 않는다."""
from __future__ import annotations
import os, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = ROOT / "web" / "public" / "data"
KST = timezone(timedelta(hours=9))
KEY_ENVS = ("ECOS_API_KEY", "FRED_API_KEY", "OPENAI_API_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.removeprefix("export ").split("=", 1)
        k, v = k.strip(), v.strip().strip("\"'")
        if k in KEY_ENVS and v and not os.environ.get(k):
            os.environ[k] = v


# FXODDS_ENV_FILE(저장소 밖 경로 권장) 또는 저장소 루트의 .env. GitHub Actions에서는 Secrets가 우선한다.
load_dotenv(Path(os.environ.get("FXODDS_ENV_FILE") or ROOT / ".env"))


def redact(text: str) -> str:
    for k in KEY_ENVS:
        v = os.environ.get(k, "")
        if len(v) >= 6:
            text = text.replace(v, "***")
    return re.sub(r"(AUTH_KEY|api_key|serviceKey)=[A-Za-z0-9%._\-]{6,}", r"\1=***", text)


def now_kst() -> datetime:
    return datetime.now(KST)


# ---------------------------------------------------------------------------------------------
# 이용 가능 시각(available_at): 관측일과 '그 값을 실제로 볼 수 있게 된 날'을 분리한다.
# 과거 시점 재현·백테스트는 available_at <= 기준일 인 자료만 쓴다.
# ---------------------------------------------------------------------------------------------
import pandas as pd

FRED_DAILY_MARKET = {"DGS2", "DGS10", "DFF", "VIXCLS", "DCOILWTICO", "DFEDTARU"}  # 다음 영업일 반영
MONTHLY_LAG_DAYS = 41  # 한국은행 국제수지(월)는 다음다음 달 초순 발표 -> 월말 + 41일로 보수적 가정


def avail_date(series: str, obs: pd.Timestamp) -> pd.Timestamp:
    """series 예: 'ecos:KRW_per_USD', 'yahoo:USDJPY', 'fred:DGS2', 'fred:USDJPY'.
    - ecos 일별: 서울 장 마감 후 당일. ecos 월별(bop:): 월말 + 41일.
    - yahoo 일봉: 런던 자정 마감이므로 관측일 다음 날.
    - fred 일별 시장지표(DGS2 등): 다음 영업일.
    - fred H.10 환율(DEX*): 주간 발표(관측 주의 다음 월요일, 추정 규칙 - H.10 일정 미확인).
    """
    obs = pd.Timestamp(obs).normalize()
    src, _, name = series.partition(":")
    if src == "ecos":
        return obs + pd.Timedelta(days=MONTHLY_LAG_DAYS) if name.startswith(("BOP_", "POLICY_", "FLOW_")) else obs
    if src == "gpr":  # GPR 지수는 사후 수정되므로 2일 보수적 지연
        return obs + pd.Timedelta(days=2)
    if src == "yahoo":
        return obs + pd.Timedelta(days=1)
    if src == "fred":
        if name in FRED_DAILY_MARKET:
            return obs + pd.offsets.BDay(1)
        # H.10: 관측 주(월~일)의 다음 월요일
        return obs + pd.Timedelta(days=7 - obs.dayofweek)
    return obs
