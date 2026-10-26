"""FX PRESSURE INDEX (FPI) v0.1 — 실험적 압력 지수. 확률이 아니다.

-100 = 강한 원화 강세 압력, 0 = 중립, +100 = 강한 원화 약세 압력.
규칙 기반: 요인별 신호(최근 20영업일 변화 또는 월별 수준)를 과거 756영업일(월별은 60개월) 분포로 z-표준화(±3 절단)해
 p = sign × z/3 × 100 으로 환산하고, 영역(10개)별로 동일가중 평균한다. 자료가 없는 영역은 0점으로 채우지 않고 제외하며 자료 충족률을 함께 보여 준다.
모든 입력은 '서울 기준일 D 에 이미 이용 가능했던(available_at <= D)' 값만 쓴다.
공통 충격 중복 방지: 한국 금리는 미국 2년 금리를, 엔·위안·대만달러는 달러 공통요인을 trailing 회귀로 제거한 잔차만 신호로 쓴다.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats
import prep, models as M
from common import avail_date

Z_WIN = 756
BETA_WIN = 252
H = 20  # 신호 창(영업일)
MAX_AGE = {"daily": 10, "monthly": 120}  # 마지막 관측이 이보다 오래되면 '자료 없음' 처리(달력일)

AREAS = [  # (id, 이름, 설명)
    ("us_policy", "미국 통화정책", "미국 2년·10년 국채금리 20일 변화"),
    ("kr_policy", "한국 통화정책", "국고채 3년 20일 변화 중 미국 2년 금리로 설명되지 않는 부분(잔차)"),
    ("usd", "글로벌 달러", "EUR·GBP·AUD·CAD·CHF·SEK 기반 달러 요인 20일 변화"),
    ("jpy", "일본 엔화", "USD/JPY 20일 변화 중 달러 요인으로 설명되지 않는 부분(잔차)"),
    ("cny", "중국 위안화", "USD/CNY 20일 변화 중 달러 요인 잔차"),
    ("twd", "대만 달러", "USD/TWD 20일 변화 중 달러 요인 잔차"),
    ("ext", "한국 대외거래", "경상수지 3개월 합(월, 발표 지연)"),
    ("flow", "자본 흐름", "외국인 증권투자 순유입(증권투자 부채) 3개월 합(월, 발표 지연)"),
    ("commod", "원자재·지정학", "WTI 20일 변화 (지정학 위험은 지표 미보유)"),
    ("market", "글로벌 금융시장", "VIX 수준과 코스피 20일 수익률"),
]


def asof_series(df: pd.DataFrame, name: str, dates: pd.DatetimeIndex):
    """df: load_long 결과. 각 서울 기준일 D 에 대해 available_at <= D 인 가장 최근 관측값과 그 관측일을 반환."""
    g = df[df.series == name].copy()
    g["avail"] = pd.to_datetime(g["available_at"]); g["obs"] = g["observed_date"]
    g = g.sort_values(["avail", "obs"]).drop_duplicates("avail", keep="last").set_index("avail")
    v = g["value"].reindex(dates.union(g.index)).ffill().reindex(dates)
    o = g["obs"].reindex(dates.union(g.index)).ffill().reindex(dates)
    return v, o


def _z(x: pd.Series, win: int, minp: int) -> pd.Series:
    m = x.rolling(win, min_periods=minp).mean(); s = x.rolling(win, min_periods=minp).std()
    return ((x - m) / s).clip(-3, 3)


def _resid(y: pd.Series, f: pd.Series, daily_y: pd.Series, daily_f: pd.Series) -> pd.Series:
    """y 의 H일 변화에서 f 의 H일 변화 × trailing beta 를 뺀 잔차. beta 는 최근 BETA_WIN 일 일별 수익률 회귀(기준일까지의 자료만)."""
    cov = daily_y.rolling(BETA_WIN, min_periods=120).cov(daily_f); var = daily_f.rolling(BETA_WIN, min_periods=120).var()
    beta = cov / var
    return y - beta * f


def compute(df: pd.DataFrame, dates: pd.DatetimeIndex) -> dict:
    """dates: 서울 기준일(ECOS 영업일). 반환 dict: panel(DataFrame), comps(요인 정의), meta."""
    v, age = {}, {}
    names = {"dgs2": "fred:DGS2", "dgs10": "fred:DGS10", "ktb": "ecos:KTB3Y", "vix": "fred:VIXCLS", "wti": "fred:DCOILWTICO", "kospi": "yahoo:KOSPI",
             "jpy": "yahoo:USDJPY", "cny": "yahoo:USDCNY", "twd": "yahoo:USDTWD"}
    for k, n in names.items():
        v[k], o = asof_series(df, n, dates); age[k] = (dates.to_series() - o).dt.days
    # 달러 요인(Yahoo): 요인통화 수익률 평균을 자체 달력에서 계산한 뒤 누적지수로 만들고 as-of 정렬
    y = prep.panel_yahoo_or_fred(df, "yahoo")
    fr = prep.dollar_factor(np.log(y).diff())
    fidx = fr.dropna().cumsum()
    fdf = pd.DataFrame({"series": "yahoo:USDFACTOR", "observed_date": fidx.index, "value": fidx.values})
    fdf["available_at"] = [avail_date("yahoo:USDFACTOR", d).strftime("%Y-%m-%d") for d in fdf.observed_date]
    v["f"], o = asof_series(fdf, "yahoo:USDFACTOR", dates); age["f"] = (dates.to_series() - o).dt.days  # 누적 로그수준

    lg = {k: (np.log(v[k]) if k in ("jpy", "cny", "twd", "wti", "kospi") else v[k]) for k in v}  # f 는 이미 로그 누적
    d1 = {k: lg[k].diff() for k in lg}

    def chg(s):
        return s - s.shift(H)

    sig = {}  # 영역/요인 -> (신호 시계열, 부호, 자료 나이 key, 'daily'|'monthly')
    sig["us2"] = (chg(lg["dgs2"]), +1, "dgs2", "daily"); sig["us10"] = (chg(lg["dgs10"]), +1, "dgs10", "daily")
    sig["kr"] = (_resid(chg(lg["ktb"]), chg(lg["dgs2"]), d1["ktb"], d1["dgs2"]), -1, "ktb", "daily")
    sig["usd"] = (chg(lg["f"]), +1, "f", "daily")
    for c in ("jpy", "cny", "twd"):
        sig[c] = (_resid(chg(lg[c]), chg(lg["f"]), d1[c], d1["f"]), +1, c, "daily")
    sig["wti"] = (chg(lg["wti"]), +1, "wti", "daily")
    sig["vix"] = (lg["vix"], +1, "vix", "daily")
    sig["kospi"] = (chg(lg["kospi"]), -1, "kospi", "daily")
    zs = {}
    for k, (s, sign, ak, kind) in sig.items():
        z = _z(s, Z_WIN, 252)
        zs[k] = z.where(age[ak] <= MAX_AGE["daily"])
    # 월별 요인(국제수지): 3개월 합 -> 과거 60개월 z -> 이용 가능일에 맞춰 정렬
    monthly = {}
    for k, n in (("ext", "ecos:BOP_CURRENT_ACCOUNT"), ("flow", "ecos:BOP_PORTFOLIO_LIAB")):
        g = df[df.series == n].sort_values("observed_date").set_index("observed_date")
        s3 = g["value"].rolling(3).sum()
        zm = ((s3 - s3.rolling(60, min_periods=36).mean().shift(1)) / s3.rolling(60, min_periods=36).std().shift(1)).clip(-3, 3)
        mdf = pd.DataFrame({"series": n, "observed_date": zm.index, "value": zm.values, "available_at": g["available_at"].values}).dropna(subset=["value"])
        zv, o = asof_series(mdf, n, dates)
        zs[k] = zv.where((dates.to_series() - o).dt.days <= MAX_AGE["monthly"])
        monthly[k] = o
        s3df = pd.DataFrame({"series": n, "observed_date": s3.index, "value": s3.values, "available_at": g["available_at"].values}).dropna(subset=["value"])
        sig[k] = (asof_series(s3df, n, dates)[0], -1, k, "monthly")
    comp_defs = {  # 영역 -> [(요인키, 부호)]
        "us_policy": [("us2", +1), ("us10", +1)], "kr_policy": [("kr", -1)], "usd": [("usd", +1)], "jpy": [("jpy", +1)], "cny": [("cny", +1)],
        "twd": [("twd", +1)], "ext": [("ext", -1)], "flow": [("flow", -1)], "commod": [("wti", +1)], "market": [("vix", +1), ("kospi", -1)],
    }
    area_p = {}
    for a, comps in comp_defs.items():
        cols = [(zs[k] * sign / 3 * 100) for k, sign in comps]
        area_p[a] = pd.concat(cols, axis=1).mean(axis=1, skipna=True)  # 구성 요인 일부만 있어도 있는 것만 평균, 전부 없으면 NaN
    panel = pd.DataFrame(area_p)
    avail = panel.notna()
    fpi = panel.mean(axis=1, skipna=True).where(avail.sum(axis=1) > 0)
    coverage = avail.mean(axis=1)
    out = pd.DataFrame({"fpi": fpi, "coverage": coverage}).join(panel)
    return {"panel": out, "z": pd.DataFrame(zs), "raw": {k: s for k, (s, _, _, _) in sig.items()}, "comp_defs": comp_defs, "age": age, "monthly_obs": monthly}


def latest_detail(res: dict, i: int, dates: pd.DatetimeIndex, df: pd.DataFrame) -> dict:
    p = res["panel"]; row = p.iloc[i]
    areas = []
    n_av = int(row[[a[0] for a in AREAS]].notna().sum())
    for aid, name, desc in AREAS:
        val = row[aid]
        comps = []
        for k, sign in res["comp_defs"][aid]:
            z = res["z"][k].iloc[i]
            comps.append({"key": k, "sign": sign, "z": None if not np.isfinite(z) else round(float(z), 2),
                          "raw": None if not np.isfinite(res["raw"][k].iloc[i]) else round(float(res["raw"][k].iloc[i]), 4)})
        areas.append({"id": aid, "name": name, "desc": desc, "p": None if not np.isfinite(val) else round(float(val), 1),
                      "contrib": None if not np.isfinite(val) or n_av == 0 else round(float(val) / n_av, 1), "components": comps})
    prev = p["fpi"].iloc[i - 1] if i > 0 else np.nan
    wk = p["fpi"].iloc[i - 5] if i >= 5 else np.nan
    return {"date": dates[i].strftime("%Y-%m-%d"), "fpi": None if not np.isfinite(row["fpi"]) else round(float(row["fpi"]), 1),
            "coverage": round(float(row["coverage"]), 2), "areas": areas, "change_1d": None if not np.isfinite(prev) or not np.isfinite(row["fpi"]) else round(float(row["fpi"] - prev), 1),
            "change_5d": None if not np.isfinite(wk) or not np.isfinite(row["fpi"]) else round(float(row["fpi"] - wk), 1)}


def validate(res: dict, ecos: pd.Series, start="2012-01-02", min_cov=0.6) -> dict:
    """FPI 의 방향 신호가 이후 7일·30일 환율 변화와 관련 있는지(표본 외가 아니라 규칙 기반이므로 전 구간 사후 점검).
    파라미터를 적합하지 않으므로 look-ahead 는 없으나, 요인 부호·구성은 사람이 정했다는 점에서 완전한 표본 외 검증은 아니다."""
    dates = ecos.index; p = res["panel"].reindex(dates)
    out = {}
    for hz in (7, 30):
        T, y = np.full(len(dates), -1), np.full(len(dates), np.nan)
        for i, d in enumerate(dates):
            td = M.target_obs(dates, d, hz)
            if td is not None:
                j = dates.get_loc(td); T[i] = j; y[i] = np.log(ecos.iloc[j] / ecos.iloc[i])
        mask = (dates >= pd.Timestamp(start)) & np.isfinite(y) & (p["coverage"].values >= min_cov) & np.isfinite(p["fpi"].values)
        x, yy = p["fpi"].values[mask], y[mask]
        h_bd = M.horizon_bd(pd.Timestamp("2026-10-26"), hz)
        # OLS 기울기 + Newey-West t
        X = np.c_[np.ones(len(x)), x]; b = np.linalg.lstsq(X, yy, rcond=None)[0]; e = yy - X @ b
        S = np.zeros((2, 2))
        for L in range(0, h_bd + 1):
            w = 1.0 if L == 0 else 1 - L / (h_bd + 1)
            G = (X[L:] * e[L:, None]).T @ (X[: len(x) - L] * e[: len(x) - L, None]) / len(x)
            S += G if L == 0 else w * (G + G.T)
        XtXi = np.linalg.inv(X.T @ X / len(x)); V = XtXi @ S @ XtXi / len(x)
        t = float(b[1] / np.sqrt(V[1, 1]))
        # 부호 적중: h_bd 간격 비중첩 표본, 이항검정
        idx = np.arange(0, len(x), max(1, h_bd))
        hits = (np.sign(x[idx]) == np.sign(yy[idx])) & (x[idx] != 0)
        n_ = int(len(idx)); k_ = int(hits.sum())
        pbin = float(stats.binomtest(k_, n_, 0.5).pvalue)
        strong = np.abs(x) >= np.quantile(np.abs(x), 0.75)
        hit_all = float((np.sign(x) == np.sign(yy)).mean()); hit_strong = float((np.sign(x[strong]) == np.sign(yy[strong])).mean())
        qs = pd.qcut(pd.Series(x), 5, labels=False, duplicates="drop")
        quint = [round(float(pd.Series(yy)[qs == q].mean() * 100), 3) for q in sorted(qs.dropna().unique())]
        yrs = pd.Series(dates[mask].year)
        by_year = {int(yv): round(float(np.corrcoef(x[(yrs == yv).values], yy[(yrs == yv).values])[0, 1]), 3) for yv in sorted(yrs.unique()) if (yrs == yv).sum() > 60}
        out[f"h{hz}"] = {"n": int(len(x)), "slope_pct_per_100": round(float(b[1] * 100 * 100), 3), "t_hac": round(t, 2), "corr": round(float(np.corrcoef(x, yy)[0, 1]), 3),
                         "hit_all": round(hit_all, 3), "hit_strong": round(hit_strong, 3), "hit_nonoverlap": round(k_ / n_, 3), "n_nonoverlap": n_, "p_binom": round(pbin, 3),
                         "quintile_mean_pct": quint, "by_year_corr": by_year}
    return out
