"""FX VOLATILITY INDEX(FXVI) 와 일중 변동성 지표. 원자료: 한국은행 ECOS 731Y003 원/달러 일별 시가·고가·저가·종가.

핵심 규칙(데이터로 확인)
- 고가·저가는 그 세션이 끝난 뒤 확정되므로 available_at = 관측일 + 1영업일. 당일 행(시가만 있고 고·저·종 없음)은 어떤 계산에도 쓰지 않는다.
- 매매기준율(731Y001)의 D일 값은 '전 영업일(D-1) 세션'의 거래를 반영한다(D일 변화율과 D-1 종가 변화율의 상관 0.84~0.88, D-1 고저 범위에 99.8% 포함).
  따라서 기준일 D 의 예측에는 D-1 세션까지의 고저만 쓰고, 장벽 돌파 관측 구간은 세션 D 부터 '평가일 전 영업일'까지다.
- 고가·저가 관측 범위가 바뀐 시점(레짐 단절)은 BREAKS 에 기록하고 모든 시계열 차트에 표시한다. FXVI 백분위는 같은 레짐 안의 252거래일로만 계산하고, 부족하면 산출하지 않는다.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats
import prep

NAMES = {"ecos:OHLC_OPEN": "O", "ecos:OHLC_HIGH": "H", "ecos:OHLC_LOW": "L", "ecos:OHLC_CLOSE1530": "C", "ecos:OHLC_CLOSE_FULL": "CF", "ecos:KRW_per_USD": "FIX"}
ANN = 252
FROM = pd.Timestamp("2005-01-03")
BREAKS = [
    {"date": "2024-07-01", "kind": "data", "label": "외환시장 마감 02:00까지 연장 — 고가·저가 관측 범위 확대",
     "evidence": "ECOS 종가(연장) 계열이 이 날 시작하고, 이후 모든 날 종가가 고가·저가 범위 안에 있음(데이터 확인)"},
    {"date": "2026-07-06", "kind": "news", "label": "원/달러 24시간 거래 개시(보도 기준, 한국은행·재정경제부 원문 미확인)",
     "evidence": "언론 보도로 시행일을 확인했고, 변동폭 수준의 통계적 단절은 아래 검정으로 점검"},
]


def ohlc(df_long: pd.DataFrame) -> pd.DataFrame:
    """열 이름으로 선택한다(prep.wide 는 열을 알파벳순으로 정렬하므로 위치로 이름을 붙이면 안 된다)."""
    w = prep.wide(df_long, list(NAMES)).rename(columns=NAMES)
    for c in ("O", "H", "L", "C", "CF", "FIX"):
        if c not in w:
            w[c] = np.nan
    w = w[["O", "H", "L", "C", "CF", "FIX"]]
    av = df_long[df_long.series == "ecos:OHLC_HIGH"].set_index("observed_date")["available_at"]
    w["avail"] = pd.to_datetime(av.reindex(w.index))
    return w


def clean(w: pd.DataFrame):
    """완결된 세션만 남긴다: 고·저·종가가 있고 H>=L, 시가·종가가 [L,H] 안. 제외한 행은 기록해 돌려준다."""
    v = w.dropna(subset=["H", "L", "C"])
    ok = (v.H >= v.L) & (v.H >= v[["O", "C"]].max(axis=1)) & (v.L <= v[["O", "C"]].min(axis=1))
    dropped = v.index[~ok]
    return v[ok & (v.index >= FROM)], [d.strftime("%Y-%m-%d") for d in dropped]


def parkinson_var(h: pd.Series, l: pd.Series) -> pd.Series:
    """일별 파킨슨 분산 = ln(H/L)^2 / (4 ln 2)."""
    return np.log(h / l) ** 2 / (4 * np.log(2))


def metrics(v: pd.DataFrame) -> pd.DataFrame:
    m = pd.DataFrame(index=v.index)
    m["H"], m["L"], m["C"], m["O"], m["FIX"] = v.H, v.L, v.C, v.O, v.FIX
    m["range_won"] = v.H - v.L
    m["range_pct"] = (v.H - v.L) / ((v.H + v.L) / 2) * 100
    for n in (5, 20, 60):
        m[f"avg{n}"] = m["range_won"].rolling(n).mean()
    m["pv"] = parkinson_var(v.H, v.L)
    m["park20_daily"] = np.sqrt(m["pv"].rolling(20).mean())            # 일 단위(로그수익률 표준편차)
    m["park20_ann"] = m["park20_daily"] * np.sqrt(ANN) * 100            # 연율화(%): ×√252
    return m


def regime_test(m: pd.DataFrame, brk="2026-07-06", pre_days=125) -> dict:
    """24시간 거래 개시일 전후의 일중 변동률(로그) 수준 차이 검정. 단절이 확인되면 새 레짐으로 본다."""
    b = pd.Timestamp(brk)
    post = np.log(m.loc[m.index >= b, "range_pct"].dropna())
    pre = np.log(m.loc[(m.index < b), "range_pct"].dropna().tail(pre_days))
    if len(post) < 20 or len(pre) < 20:
        return {"n_post": int(len(post)), "n_pre": int(len(pre)), "significant": None, "note": "표본 부족"}
    t = stats.ttest_ind(post, pre, equal_var=False); u = stats.mannwhitneyu(post, pre)
    shift = float(np.exp(post.mean() - pre.mean()) - 1) * 100
    return {"n_post": int(len(post)), "n_pre": int(len(pre)), "median_pre": round(float(np.exp(pre.median())), 3), "median_post": round(float(np.exp(post.median())), 3),
            "shift_pct": round(shift, 1), "p_welch": round(float(t.pvalue), 4), "p_mwu": round(float(u.pvalue), 4), "significant": bool(min(t.pvalue, u.pvalue) < 0.01)}


def regime_starts(m: pd.DataFrame, test: dict) -> list[pd.Timestamp]:
    s = [pd.Timestamp(BREAKS[0]["date"])]
    if test.get("significant"):
        s.append(pd.Timestamp(BREAKS[1]["date"]))
    return s


def fxvi(m: pd.DataFrame, starts: list[pd.Timestamp], win=252) -> pd.Series:
    """FXVI = 최근 20일 파킨슨 변동성이 '같은 레짐' 안 과거 252거래일 분포에서 차지하는 백분위(0~100). 부족하면 NaN."""
    p = m["park20_daily"]
    out = pd.Series(np.nan, index=m.index)
    for i, (d, val) in enumerate(p.items()):
        if not np.isfinite(val):
            continue
        rs = max([s for s in starts if s <= d], default=FROM)
        seg = p.loc[(p.index >= rs) & (p.index <= d)].dropna().tail(win)
        if len(seg) < win:
            continue
        out.iloc[i] = ((seg < val).sum() + 0.5 * (seg == val).sum()) / len(seg) * 100
    return out


def regime_of(d: pd.Timestamp) -> str:
    return "2024-07 이후(02:00 마감)" if d >= pd.Timestamp(BREAKS[0]["date"]) else "2024-07 이전(09:00~15:30)"


def commentary(m: pd.DataFrame, fx: pd.Series, test: dict) -> list[str]:
    out = []
    last = m.index[-1]
    r = m.loc[last]
    f = fx.dropna()
    if len(f) and f.index[-1] == last:
        pct = f.iloc[-1]
        word = "상위" if pct >= 50 else "하위"
        rank = 100 - pct if pct >= 50 else pct
        out.append(f"최근 20거래일 환율 변동성(파킨슨)은 같은 구간 최근 252거래일 중 {word} {rank:.0f}% 수준입니다(FXVI {pct:.0f}).")
    elif len(f) == 0:
        out.append("FXVI는 같은 관측 구간의 기초 자료(252거래일)가 부족해 산출하지 않았습니다.")
    a20 = m["range_won"].iloc[-21:-1].mean() if len(m) > 21 else np.nan
    if np.isfinite(a20) and a20 > 0:
        d = (r.range_won / a20 - 1) * 100
        out.append(f"{last:%m월 %d일} 고가와 저가의 차이({r.range_won:.1f}원)는 직전 20거래일 평균({a20:.1f}원)보다 {abs(d):.0f}% {'큽니다' if d >= 0 else '작습니다'}.")
    if len(m) > 252:
        yr = m["range_won"].iloc[-252:]
        prev = m["range_won"].iloc[-504:-252]
        if len(prev) > 100:
            out.append(f"최근 1년 평균 일중 변동폭은 {yr.mean():.1f}원으로 그 전 1년({prev.mean():.1f}원)보다 {abs(yr.mean() / prev.mean() - 1) * 100:.0f}% {'넓습니다' if yr.mean() >= prev.mean() else '좁습니다'}. 2024-07 마감 연장으로 관측 범위가 넓어진 영향이 섞여 있습니다.")
    if test.get("significant") is False:
        out.append(f"2026-07-06 24시간 거래 개시 전후 일중 변동률 수준에는 통계적으로 뚜렷한 단절이 확인되지 않았습니다(p={test['p_welch']}).")
    elif test.get("significant"):
        out.append("2026-07-06 24시간 거래 개시 전후로 일중 변동률 수준이 달라져 새 관측 구간으로 분리했습니다.")
    out.append("변동성이 높다는 것은 움직임의 크기가 컸다는 뜻이며, 환율이 오를 가능성이 높다는 뜻이 아닙니다.")
    return out
