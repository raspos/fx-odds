"""환율 수집기. 출처별 원시 응답을 data/raw에 저장하고 data/fx.sqlite(long 형식)에 적재한다.

출처(우선순위)
  ecos   : 한국은행 ECOS 731Y001 (매매기준율, 서울 15:30 부근 기준) - USD/KRW 기준 시계열, 대원화 교차환율
  fred   : (미사용) FRED DEXKOUS/DEXJPUS/DEXCHUS/DEXTAUS (뉴욕 정오 매입환율). 접속 가능한 환경에서만 사용
  yahoo  : Yahoo Finance 일봉 종가 (비공식, 런던/뉴욕 마감 부근). JPY·CNY·TWD·달러요인 통화
적재 규칙: 값이 양수가 아니면 버리고, 주말 행은 버린다. 출처를 섞어 한 시계열로 합치지 않는다.
"""
from __future__ import annotations
import json, os, sqlite3, sys, time
from datetime import datetime, timezone
import pandas as pd
import requests
from common import RAW, DATA, redact, avail_date

UA = {"User-Agent": "Mozilla/5.0 (fx-odds data collector)"}
DB = DATA / "fx.sqlite"

# series 이름: <출처>:<코드>. 방향은 모두 '1단위 외화(또는 USD)당 가치' 원본 그대로 저장하고, 방향 통일은 prep.py에서 한다.
ECOS_ITEMS = {  # 731Y001 항목코드 -> (이름, 단위 메모)
    "0000001": ("ecos:KRW_per_USD", "원/달러 매매기준율"),
    "0000053": ("ecos:KRW_per_CNY", "원/위안 매매기준율(2016~)"),
    "0000002": ("ecos:KRW_per_100JPY", "원/100엔 매매기준율 (100엔 단위!)"),
    "0000031": ("ecos:KRW_per_TWD", "원/대만달러(2015~)"),
}
YAHOO = {  # 심볼 -> series 이름. 모두 'USD 1단위당 외화' 형태로 정규화는 prep.py에서
    "KRW=X": "yahoo:USDKRW", "JPY=X": "yahoo:USDJPY", "CNY=X": "yahoo:USDCNY", "TWD=X": "yahoo:USDTWD",
    "EURUSD=X": "yahoo:EURUSD", "GBPUSD=X": "yahoo:GBPUSD", "AUDUSD=X": "yahoo:AUDUSD",
    "CAD=X": "yahoo:USDCAD", "CHF=X": "yahoo:USDCHF", "SEK=X": "yahoo:USDSEK",
    "^KS11": "yahoo:KOSPI", "^TNX": "yahoo:UST10Y", "^FVX": "yahoo:UST5Y", "^VIX": "yahoo:VIX", "CL=F": "yahoo:WTI",
}
FRED = {"DEXKOUS": "fred:USDKRW", "DEXJPUS": "fred:USDJPY", "DEXCHUS": "fred:USDCNY", "DEXTAUS": "fred:USDTWD",
        # 달러 공통요인(아시아 통화 제외) 구성용
        "DEXUSEU": "fred:EURUSD", "DEXUSUK": "fred:GBPUSD", "DEXUSAL": "fred:AUDUSD",
        "DEXCAUS": "fred:USDCAD", "DEXSZUS": "fred:USDCHF", "DEXSDUS": "fred:USDSEK",
        # FPI 요인(미국 금리·변동성·유가). 일별 시장지표라 다음 영업일에 이용 가능
        "DGS2": "fred:DGS2", "DGS10": "fred:DGS10", "DFF": "fred:DFF", "VIXCLS": "fred:VIXCLS", "DCOILWTICO": "fred:DCOILWTICO",
        "DFEDTARU": "fred:DFEDTARU"}


def _store(rows: pd.DataFrame, name: str, source: str, weekdays_only: bool = True) -> int:
    """rows: DataFrame[observed_date(str), value]. 검증 후 SQLite에 교체 적재."""
    df = rows.copy()
    df["observed_date"] = pd.to_datetime(df["observed_date"])
    df = df[(df["value"] > 0) & df["value"].notna()]
    if weekdays_only:
        df = df[df["observed_date"].dt.dayofweek < 5]
    df = df.drop_duplicates("observed_date").sort_values("observed_date")
    df["available_at"] = [avail_date(name, d).strftime("%Y-%m-%d") for d in df["observed_date"]]
    df["observed_date"] = df["observed_date"].dt.strftime("%Y-%m-%d")
    df["series"], df["source"] = name, source
    df["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS obs(series TEXT, observed_date TEXT, value REAL, source TEXT,
                   fetched_at TEXT, available_at TEXT, PRIMARY KEY(series, observed_date))""")
    if "available_at" not in [r[1] for r in con.execute("PRAGMA table_info(obs)")]:
        con.execute("ALTER TABLE obs ADD COLUMN available_at TEXT")
    con.execute("DELETE FROM obs WHERE series=?", (name,))
    df[["series", "observed_date", "value", "source", "fetched_at", "available_at"]].to_sql("obs", con, if_exists="append", index=False)
    con.commit(); con.close()
    return len(df)


ECOS_RATES = {  # (stat, cycle, item) -> 이름
    ("817Y002", "D", "010200000"): "ecos:KTB3Y", ("722Y001", "D", "0101000"): "ecos:BASE_RATE",
    ("301Y017", "M", "SA000"): "ecos:BOP_CURRENT_ACCOUNT",       # 경상수지(월, 백만달러)
    ("301Y017", "M", "SA110"): "ecos:BOP_EXPORTS",
    ("301Y013", "M", "BOPF22000000"): "ecos:BOP_PORTFOLIO_LIAB",  # 증권투자(부채) = 외국인의 국내 증권투자 순유입(월)
}


def fetch_ecos_rates(start="20000101") -> dict:
    key = os.environ.get("ECOS_API_KEY")
    if not key:
        return {"ok": False, "why": "ECOS_API_KEY 없음"}
    res = {}
    for (stat, cyc, item), name in ECOS_RATES.items():
        try:
            s_, e_ = (start, datetime.now().strftime("%Y%m%d")) if cyc == "D" else (start[:6], datetime.now().strftime("%Y%m"))
            url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100000/{stat}/{cyc}/{s_}/{e_}/{item}"
            j = requests.get(url, headers=UA, timeout=60).json()
            rows = j.get("StatisticSearch", {}).get("row", [])
            if not rows:
                res[name] = f"fail: {redact(str(j))[:120]}"; continue
            (RAW / f"{name.replace(':', '_')}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            df = pd.DataFrame({"observed_date": [r["TIME"] for r in rows], "value": [float(r["DATA_VALUE"]) for r in rows]})
            if cyc == "D":
                df["observed_date"] = pd.to_datetime(df["observed_date"], format="%Y%m%d")
                res[name] = _store(df, name, "ecos")
            else:  # 월별: 관측일 = 해당 월 말일
                df["observed_date"] = pd.to_datetime(df["observed_date"], format="%Y%m") + pd.offsets.MonthEnd(0)
                res[name] = _store(df, name, "ecos", weekdays_only=False)
        except Exception as e:
            res[name] = "fail: " + redact(str(e))[:120]
    return res


def fetch_ecos(start="20000101") -> dict:
    key = os.environ.get("ECOS_API_KEY")
    if not key:
        return {"ok": False, "why": "ECOS_API_KEY 없음"}
    res = {}
    end = datetime.now().strftime("%Y%m%d")
    for code, (name, _) in ECOS_ITEMS.items():
        try:
            url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100000/731Y001/D/{start}/{end}/{code}"
            j = requests.get(url, headers=UA, timeout=60).json()
            rows = j.get("StatisticSearch", {}).get("row", [])
            if not rows:
                res[name] = f"fail: {redact(str(j))[:120]}"; continue
            (RAW / f"{name.replace(':', '_')}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            df = pd.DataFrame({"observed_date": [r["TIME"] for r in rows], "value": [float(r["DATA_VALUE"]) for r in rows]})
            df["observed_date"] = pd.to_datetime(df["observed_date"], format="%Y%m%d")
            res[name] = _store(df, name, "ecos")
        except Exception as e:
            res[name] = "fail: " + redact(str(e))[:120]
    return res


def fetch_yahoo(range_="max") -> dict:
    res = {}
    for sym, name in YAHOO.items():
        got = None
        for attempt in range(4):
            try:
                host = "query2" if attempt % 2 == 0 else "query1"
                r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}",
                                 params={"period1": 1041379200, "period2": int(time.time()) + 86400, "interval": "1d"}, headers=UA, timeout=45)
                if r.status_code != 200:
                    time.sleep(3 * (attempt + 1)); continue
                got = r.json()["chart"]["result"][0]; break
            except Exception:
                time.sleep(3 * (attempt + 1))
        if not got:
            res[name] = "fail"; continue
        (RAW / f"{name.replace(':', '_')}.json").write_text(json.dumps(got), encoding="utf-8")
        ts = got["timestamp"]; close = got["indicators"]["quote"][0]["close"]
        # 런던 자정 봉(UTC 23:00/00:00)을 해당 거래일로 정렬하려고 6시간을 더한다
        df = pd.DataFrame({"observed_date": (pd.to_datetime(ts, unit="s") + pd.Timedelta(hours=6)).normalize(), "value": close}).dropna()
        # 오늘(UTC) 봉은 장중 미완성이므로 제외
        df = df[df["observed_date"] < pd.Timestamp(datetime.now(timezone.utc).date())]
        res[name] = _store(df, name, "yahoo")
        time.sleep(1.2)
    return res


def fetch_fred() -> dict:
    res = {}
    for sid, name in FRED.items():
        try:
            r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": sid, "cosd": "2000-01-01"},
                             headers=UA, timeout=(10, 40))
            r.raise_for_status()
            df = pd.read_csv(pd.io.common.StringIO(r.text))
            df.columns = ["observed_date", "value"]
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            (RAW / f"{name.replace(':', '_')}.csv").write_text(r.text, encoding="utf-8")
            res[name] = _store(df.dropna(), name, "fred")
        except Exception as e:
            res[name] = "fail: " + redact(type(e).__name__)
    return res


def run() -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    return {"ecos": {**fetch_ecos(), **fetch_ecos_rates()}, "yahoo": fetch_yahoo()}  # FRED는 사용하지 않는다(fetch_fred 는 보관만)


if __name__ == "__main__":
    out = run()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (DATA / "fetch_status.json").write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **out},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
