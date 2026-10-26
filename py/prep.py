"""적재된 원시 시계열을 분석용 패널로 정리한다. 모든 환율은 'USD 1단위당 외화(=값이 클수록 외화 약세, 달러 강세)'로 방향을 통일한다."""
from __future__ import annotations
import sqlite3
import numpy as np
import pandas as pd
from common import DATA

DB = DATA / "fx.sqlite"
ASIA = ["KRW", "JPY", "CNY", "TWD"]
# 달러 공통요인 구성 통화 (아시아 4개 통화 제외). inverse=True: 원자료가 'USD per 외화'라서 역수를 취해 USD당 외화로 맞춘다.
FACTOR_CCY = {"EUR": True, "GBP": True, "AUD": True, "CAD": False, "CHF": False, "SEK": False}


def load_long() -> pd.DataFrame:
    con = sqlite3.connect(DB)
    df = pd.read_sql("select series, observed_date, value, source, fetched_at, available_at from obs", con, parse_dates=["observed_date"])
    con.close()
    return df


def wide(df: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    sub = df[df.series.isin(names)].pivot(index="observed_date", columns="series", values="value")
    return sub.sort_index()


def usd_per_foreign_to_foreign_per_usd(x: pd.Series) -> pd.Series:
    return 1.0 / x


def panel_yahoo_or_fred(df: pd.DataFrame, src: str) -> pd.DataFrame:
    """src='fred'|'yahoo'. 반환: 열 KRW/JPY/CNY/TWD(USD당 외화) + 요인 통화(USD당 외화)."""
    w = wide(df, [f"{src}:USD{c}" for c in ASIA] + [f"{src}:{c}USD" for c in ("EUR", "GBP", "AUD")] +
             [f"{src}:USD{c}" for c in ("CAD", "CHF", "SEK")])
    out = pd.DataFrame(index=w.index)
    for c in ASIA:
        out[c] = w[f"{src}:USD{c}"]
    for c, inv in FACTOR_CCY.items():
        col = f"{src}:{c}USD" if inv else f"{src}:USD{c}"
        out[c] = 1.0 / w[col] if inv else w[col]
    return out


def panel_ecos(df: pd.DataFrame) -> pd.DataFrame:
    """서울 매매기준율. 단위: KRW per USD, KRW per 100JPY -> KRW per JPY로 환산(100엔 단위 혼동 방지)."""
    w = wide(df, ["ecos:KRW_per_USD", "ecos:KRW_per_100JPY", "ecos:KRW_per_CNY", "ecos:KRW_per_TWD"])
    return pd.DataFrame({
        "KRW": w["ecos:KRW_per_USD"],
        "KRW_per_JPY": w["ecos:KRW_per_100JPY"] / 100.0,
        "KRW_per_CNY": w["ecos:KRW_per_CNY"],
        "KRW_per_TWD": w["ecos:KRW_per_TWD"],
    })


def logret(p: pd.DataFrame) -> pd.DataFrame:
    return np.log(p).diff().dropna(how="all")


def dollar_factor(ret: pd.DataFrame) -> pd.Series:
    """달러 공통요인 = 6개 비아시아 통화의 USD당 외화 로그수익률 단순평균 (양수 = 달러 강세). 한·일·중·대만 통화는 포함하지 않는다."""
    cols = list(FACTOR_CCY)
    return ret[cols].mean(axis=1, skipna=False).rename("USD_FACTOR")


def cross_check_krw(df: pd.DataFrame) -> dict:
    """ECOS vs Yahoo vs FRED USD/KRW 일치도 (수준 차이 + 일별 수익률 상관, 시차별)."""
    e = wide(df, ["ecos:KRW_per_USD"]).iloc[:, 0]
    out = {}
    for src in ("yahoo", "fred"):
        s = wide(df, [f"{src}:USDKRW"]).iloc[:, 0]
        j = pd.concat([e, s], axis=1, keys=["e", "s"]).dropna()
        j = j[j.index >= j.index.max() - pd.Timedelta(days=730)]
        d = (j.s / j.e - 1) * 100
        lags = {}
        re, rs = np.log(e).diff(), np.log(s).diff()
        for k in (-1, 0, 1):
            jj = pd.concat([re, rs.shift(k)], axis=1).dropna()
            jj = jj[jj.index >= jj.index.max() - pd.Timedelta(days=730)]
            lags[str(k)] = round(float(jj.corr().iloc[0, 1]), 3)
        out[src] = {"n": int(len(j)), "mean_diff_pct": round(float(d.mean()), 3), "mean_abs_diff_pct": round(float(d.abs().mean()), 3),
                    "max_abs_diff_pct": round(float(d.abs().max()), 2), "ret_corr_by_shift": lags}
    return out
