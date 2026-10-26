"""한국투자증권(KIS) Open API — 시장별 투자자매매동향(일별) [국내주식-075], TR ID FHPTJ04040000.

외국인 코스피·코스닥 순매수 거래대금(frgn_ntby_tr_pbmn, 백만원)을 일별로 수집해 data/fx.sqlite 에 적재한다.
키: KIS_APP_KEY / KIS_APP_SECRET (KIS 개발자센터에서 앱키 발급). 키가 없으면 건너뛴다(FPI 자본흐름은 월별 통계만 사용).
이용약관: 원시 일별 수치를 그대로 재배포하지 않고, 사이트에는 파생 지표(FPI 요인 압력)만 공개한다.
이 값은 '외국인 증권 순매수 압력'이며 외국인 자본 유입액·달러 유입액이 아니다(원화 자금 매수, 환헤지 여부에 따라 환율 영향이 다르다).
"""
from __future__ import annotations
import json, os, time
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests
from common import RAW, redact, now_kst
import fetch

BASE = "https://openapi.koreainvestment.com:9443"
API = "/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market"
TR_ID = "FHPTJ04040000"
MARKETS = {"KOSPI": ("0001", "KSP"), "KOSDAQ": ("1001", "KSQ")}  # (업종코드, 시장코드)
TOKEN_CACHE = RAW / "kis_token.json"  # data/raw 는 커밋하지 않는다
MAX_PER_RUN = 450  # 1회 실행당 최대 호출 수(초기 백필은 여러 번에 나눠 진행)


def token() -> str:
    key, sec = os.environ["KIS_APP_KEY"], os.environ["KIS_APP_SECRET"]
    if TOKEN_CACHE.exists():
        c = json.loads(TOKEN_CACHE.read_text())
        if c.get("exp", 0) > time.time() + 600:
            return c["token"]
    r = requests.post(f"{BASE}/oauth2/tokenP", json={"grant_type": "client_credentials", "appkey": key, "appsecret": sec}, timeout=30)
    r.raise_for_status()
    j = r.json()
    t = j["access_token"]
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps({"token": t, "exp": time.time() + int(j.get("expires_in", 86000))}))
    return t


def parse_rows(output: list[dict]) -> list[tuple[str, float]]:
    """응답 output 에서 (영업일, 외국인 순매수 거래대금[백만원]) 목록을 뽑는다."""
    out = []
    for row in output or []:
        d, v = row.get("stck_bsop_date"), row.get("frgn_ntby_tr_pbmn")
        if not d or v in (None, ""):
            continue
        try:
            out.append((d, float(v)))
        except ValueError:
            continue
    return out


def fetch_day(tok: str, market: str, day: str) -> list[tuple[str, float]]:
    iscd, mkt = MARKETS[market]
    h = {"authorization": f"Bearer {tok}", "appkey": os.environ["KIS_APP_KEY"], "appsecret": os.environ["KIS_APP_SECRET"], "tr_id": TR_ID, "custtype": "P"}
    p = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": iscd, "FID_INPUT_DATE_1": day, "FID_INPUT_ISCD_1": mkt, "FID_INPUT_DATE_2": day, "FID_INPUT_ISCD_2": iscd}
    r = requests.get(BASE + API, headers=h, params=p, timeout=30)
    r.raise_for_status()
    j = r.json()
    if j.get("rt_cd") not in (None, "0"):
        raise RuntimeError(f"KIS {j.get('msg_cd')}: {j.get('msg1')}")
    out = j.get("output")
    return parse_rows(out if isinstance(out, list) else [out] if out else [])


def collect(start="2012-01-02") -> dict:
    if not (os.environ.get("KIS_APP_KEY") and os.environ.get("KIS_APP_SECRET")):
        return {"ok": False, "why": "KIS_APP_KEY/SECRET 없음(건너뜀)"}
    import sqlite3
    con = sqlite3.connect(fetch.DB)
    have = {m: set() for m in MARKETS}
    try:
        for m in MARKETS:
            have[m] = {r[0] for r in con.execute("select observed_date from obs where series=?", (f"kis:FRGN_NET_{m}",))}
    except sqlite3.OperationalError:
        pass
    con.close()
    today = now_kst().date()
    days = [d for d in pd.bdate_range(start, today - timedelta(days=1))]
    # 최근 날짜부터 채워서 FPI 가 빨리 쓰이게 하고, 백필은 뒤로 진행
    todo = [(m, d) for d in reversed(days) for m in MARKETS if d.strftime("%Y-%m-%d") not in have[m]][:MAX_PER_RUN]
    if not todo:
        return {"ok": True, "added": 0}
    try:
        tok = token()
    except Exception as e:
        return {"ok": False, "why": "토큰 발급 실패: " + redact(type(e).__name__ + " " + str(e))[:120]}
    rows = {m: {} for m in MARKETS}
    errs = 0
    for m, d in todo:
        try:
            for day, v in fetch_day(tok, m, d.strftime("%Y%m%d")):
                rows[m][day] = v
        except Exception as e:
            errs += 1
            if errs > 8:
                return {"ok": False, "why": "연속 오류: " + redact(str(e))[:120]}
        time.sleep(0.12)  # 초당 호출 제한 여유
    added = 0
    for m, dd in rows.items():
        if not dd:
            continue
        df = pd.DataFrame({"observed_date": pd.to_datetime(list(dd), format="%Y%m%d"), "value": list(dd.values())})
        # _store 는 시리즈를 교체하므로 기존분과 합쳐서 저장
        con = sqlite3.connect(fetch.DB)
        old = pd.read_sql("select observed_date, value from obs where series=?", con, params=(f"kis:FRGN_NET_{m}",), parse_dates=["observed_date"])
        con.close()
        both = pd.concat([old, df]).drop_duplicates("observed_date", keep="last")
        # 순매수는 음수가 가능하므로 양수 필터를 우회해 직접 적재
        added += _store_signed(both, f"kis:FRGN_NET_{m}")
    return {"ok": True, "added": added, "remaining": max(0, len([1 for d in days for m in MARKETS if d.strftime('%Y-%m-%d') not in have[m]]) - len(todo))}


def _store_signed(df: pd.DataFrame, name: str) -> int:
    import sqlite3
    from common import avail_date
    df = df.copy(); df["observed_date"] = pd.to_datetime(df["observed_date"])
    df = df[df["observed_date"].dt.dayofweek < 5].sort_values("observed_date")
    df["series"], df["source"] = name, "kis"
    df["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    df["available_at"] = [avail_date(name, d).strftime("%Y-%m-%d") for d in df["observed_date"]]
    df["observed_date"] = df["observed_date"].dt.strftime("%Y-%m-%d")
    con = sqlite3.connect(fetch.DB)
    con.execute("DELETE FROM obs WHERE series=?", (name,))
    df[["series", "observed_date", "value", "source", "fetched_at", "available_at"]].to_sql("obs", con, if_exists="append", index=False)
    con.commit(); con.close()
    return len(df)
