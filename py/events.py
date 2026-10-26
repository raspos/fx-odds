"""시장 사건 타임라인(v0.1): 공식 통계·시장 데이터에서 규칙으로 추출한 사건.

뉴스·보고서 수집 엔진(FX INTELLIGENCE)은 아직 없다. 여기서 다루는 사건은 (1) 한국은행 기준금리 변경, (2) 원화·달러 요인·미국 금리·VIX·유가의 이례적 급변동이며
각 사건에 관측일·이용 가능일·출처 URL을 붙인다. 원인(뉴스)·'예상 대비'는 수집하지 않으므로 '미보유'로 표시한다.
같은 날 같은 달러 충격으로 묶이는 사건은 하나의 사건 그룹으로 합치고 강도는 합산하지 않는다(max).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import prep
from common import avail_date

SRC = {
    "ecos_base": ("한국은행 ECOS 722Y001 기준금리", "https://ecos.bok.or.kr/"),
    "ecos_fx": ("한국은행 ECOS 731Y001 원/달러 매매기준율", "https://ecos.bok.or.kr/"),
    "yahoo_fx": ("Yahoo Finance 일봉(비공식) 달러 요인 구성 통화", "https://finance.yahoo.com/"),
    "fred_dgs10": ("Yahoo Finance ^TNX 미국 10년 국채금리(비공식)", "https://finance.yahoo.com/quote/%5ETNX/"),
    "fred_vix": ("Yahoo Finance ^VIX", "https://finance.yahoo.com/quote/%5EVIX/"),
    "fred_wti": ("Yahoo Finance CL=F WTI 원유(비공식)", "https://finance.yahoo.com/quote/CL%3DF/"),
}
CATS = {"krw": "원화", "usd": "달러", "jpy": "엔화", "us_rates": "미국 금리", "kr_rates": "한국 금리", "risk": "위험회피", "oil": "유가"}


def _ew_sigma(r: pd.Series, lam=0.94) -> pd.Series:
    v = r.var()
    out = []
    for x in r.fillna(0).values:
        out.append(np.sqrt(v)); v = lam * v + (1 - lam) * x * x  # 당일 변동 전 정보만으로 만든 σ
    return pd.Series(out, index=r.index)


def build(df: pd.DataFrame, since="2023-01-01") -> list[dict]:
    ev = []
    ecos = prep.panel_ecos(df)["KRW"].dropna()
    # 1) 정책금리 변경
    def steps(name, scale, label, srckey, cat, sign):
        g = df[df.series == name].sort_values("observed_date").set_index("observed_date").value
        ch = g.diff(); ch = ch[(ch.abs() > 1e-9)]
        for d, x in ch.items():
            if d < pd.Timestamp(since):
                continue
            up = x > 0
            ev.append({"date": d, "avail": avail_date(name, d), "kind": label, "cats": [cat], "src": srckey,
                       "title": f"{label} {g.shift(1).loc[d]:.2f}% → {g.loc[d]:.2f}% ({'인상' if up else '인하'} {abs(x) * 100:.0f}bp)",
                       "dir": ("up" if up else "down") if sign > 0 else ("down" if up else "up"), "strength": min(3, 1 + int(abs(x) * 100 // 25)),
                       "why": ("미국 금리 상승은 달러 강세·원화 약세 압력으로 작용하는 것이 일반적입니다." if cat == "us_rates" and up else
                               "미국 금리 하락은 달러 약세·원화 강세 압력으로 작용하는 것이 일반적입니다." if cat == "us_rates" else
                               "한국 금리 인상은 내외금리차를 좁혀 원화 강세 압력으로 작용하는 것이 일반적입니다." if up else
                               "한국 금리 인하는 내외금리차를 넓혀 원화 약세 압력으로 작용하는 것이 일반적입니다.")})
    cat = "kr_rates"; steps("ecos:BASE_RATE", 1, "한국은행 기준금리 변경", "ecos_base", cat, -1)

    # 2) 시장 급변동(데이터로 추출)
    y = prep.panel_yahoo_or_fred(df, "yahoo")
    fr = prep.dollar_factor(np.log(y).diff()).dropna()
    rk = np.log(ecos).diff().dropna()
    sk, sf = _ew_sigma(rk), _ew_sigma(fr)
    zk, zf = rk / sk, fr / sf
    usd_days = set(zf[zf.abs() >= 2.5].index)
    fx_avail = lambda d: d  # ECOS 당일
    def add(d, kind, cats, srckey, title, dirn, strength, why, avail):
        ev.append({"date": d, "avail": avail, "kind": kind, "cats": cats, "src": srckey, "title": title, "dir": dirn, "strength": strength, "why": why})
    for d, z in zf[zf.abs() >= 2.5].items():
        if d < pd.Timestamp(since): continue
        add(d, "usd_shock", ["usd"], "yahoo_fx", f"달러 요인 {'강세' if z > 0 else '약세'} 급변 (일간 {fr.loc[d] * 100:+.2f}%, 평소의 {abs(z):.1f}배)", "up" if z > 0 else "down",
            min(3, int(abs(z) // 1.5)), "EUR·GBP·AUD·CAD·CHF·SEK 가 같은 방향으로 크게 움직였습니다. 달러 강세는 원화 약세 압력, 달러 약세는 원화 강세 압력입니다.", avail_date("yahoo:USDFACTOR", d))
    for d, z in zk[zk.abs() >= 2.5].items():
        if d < pd.Timestamp(since): continue
        with_usd = any(abs((d - u).days) <= 1 for u in usd_days)
        add(d, "krw_shock", ["krw"], "ecos_fx", f"원/달러 {'상승' if z > 0 else '하락'} 급변 ({rk.loc[d] * 100:+.2f}%, 평소의 {abs(z):.1f}배)", "up" if z > 0 else "down", min(3, int(abs(z) // 1.5)),
            "공통 달러 요인과 같은 날(±1일) 움직였습니다. 원화 고유 요인만의 충격으로 보기 어렵습니다." if with_usd else "달러 요인 급변 없이 원화가 홀로 크게 움직였습니다. 원화 고유(국내 수급·정책·위험) 요인 가능성이 있으나 원인 뉴스는 수집되지 않았습니다.",
            avail_date("ecos:KRW_per_USD", d))
    g10 = df[df.series == "yahoo:UST10Y"].sort_values("observed_date").set_index("observed_date").value.diff().dropna()
    for d, x in g10[g10.abs() >= 0.15].items():
        if d < pd.Timestamp(since): continue
        add(d, "us10y", ["us_rates"], "fred_dgs10", f"미국 10년 금리 {'급등' if x > 0 else '급락'} ({x * 100:+.0f}bp)", "up" if x > 0 else "down", 2 if abs(x) < 0.25 else 3,
            "미국 장기금리 상승은 달러 강세·원화 약세 압력, 하락은 반대 방향 압력으로 작용하는 것이 일반적입니다.", avail_date("yahoo:UST10Y", d))
    vx = df[df.series == "yahoo:VIX"].sort_values("observed_date").set_index("observed_date").value
    vch = np.log(vx).diff()
    for d, x in vch[(vch >= np.log(1.25)) & (vx >= 20)].items():
        if d < pd.Timestamp(since): continue
        add(d, "vix", ["risk"], "fred_vix", f"VIX 급등 ({vx.loc[d]:.1f}, 전일비 {np.expm1(x) * 100:+.0f}%)", "up", 2 if vx.loc[d] < 30 else 3,
            "위험회피 심리 확대는 원화 약세 압력으로 작용하는 경향이 있습니다.", avail_date("yahoo:VIX", d))
    wt = df[df.series == "yahoo:WTI"].sort_values("observed_date").set_index("observed_date").value
    wr = np.log(wt[wt > 0]).diff()
    for d, x in wr[wr.abs() >= 0.06].items():
        if d < pd.Timestamp(since): continue
        add(d, "oil", ["oil"], "fred_wti", f"WTI 원유 {'급등' if x > 0 else '급락'} ({np.expm1(x) * 100:+.1f}%)", "up" if x > 0 else "down", 2,
            "원유 수입국인 한국에는 유가 상승이 원화 약세 압력으로 작용하는 것이 일반적입니다.", avail_date("yahoo:WTI", d))
    # 3) 사건 그룹: 같은 날(±1일) 달러·원화·엔·미국 금리 충격은 하나의 '달러 충격' 그룹으로 묶는다(점수 합산 금지)
    ev.sort(key=lambda e: e["date"])
    groups = []
    for e in ev:
        merged = False
        if set(e["cats"]) & {"usd", "krw", "us_rates", "jpy"} and e["kind"] in ("usd_shock", "krw_shock", "us10y"):
            for g in reversed(groups[-6:]):
                if g["kind_group"] == "dollar" and abs((e["date"] - g["date"]).days) <= 1:
                    g["members"].append(e); g["strength"] = max(g["strength"], e["strength"]); merged = True; break
        if not merged:
            groups.append({**e, "kind_group": "dollar" if e["kind"] in ("usd_shock", "krw_shock", "us10y") else e["kind"], "members": [e]})
    out = []
    for i, g in enumerate(groups):
        mem = g["members"]
        title = g["title"] if len(mem) == 1 else "달러 충격 동반 변동: " + " · ".join(m["title"] for m in mem)
        cats = sorted({c for m in mem for c in m["cats"]})
        why = g["why"] if len(mem) == 1 else "같은 날 여러 시장이 한 번의 달러·금리 충격으로 함께 움직였습니다. 하나의 사건으로 묶었고 강도를 합산하지 않았습니다. " + mem[0]["why"]
        dirs = {m["dir"] for m in mem}
        out.append({"id": f"{g['date']:%Y%m%d}-{i}", "date": f"{g['date']:%Y-%m-%d}", "available_at": f"{max(m['avail'] for m in mem):%Y-%m-%d}", "title": title, "cats": cats,
                    "direction": "krw_weak" if dirs == {"up"} else "krw_strong" if dirs == {"down"} else "mixed",
                    "direction_note": "원화 약세 압력(환율 상승 쪽)" if dirs == {"up"} else "원화 강세 압력(환율 하락 쪽)" if dirs == {"down"} else "판단 유보(방향 혼재)",
                    "strength": int(g["strength"]), "why": why, "sources": [{"name": SRC[m["src"]][0], "url": SRC[m["src"]][1]} for m in mem],
                    "expected_vs_actual": "미보유", "cause": "미보유(뉴스·보고서 수집 엔진 미구현)", "n_members": len(mem)})
    return sorted(out, key=lambda x: x["date"], reverse=True)
