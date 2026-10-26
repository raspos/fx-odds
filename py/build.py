"""분석 엔진 진입점: 수집 데이터 -> 백테스트 -> 최신 전망 -> 레이더 -> web/public/data/*.json.
방문자마다 계산하지 않고, 정해진 시간에 한 번 계산해 정적 JSON으로 제공한다."""
from __future__ import annotations
import json, sys
import numpy as np
import pandas as pd
from scipy import stats
import prep, models as M, backtest as B, radar, fpi as F, events as EV
import pandas as pd  # noqa
from common import DATA, OUT, now_kst

ZERO_GRID = np.round(np.arange(-0.10, 0.1001, 0.0025), 4)
MODEL_NAMES = {**M.MODELS, **{k: "조건부(릿지) " + v[0] for k, v in B.COND.items()}}
OFFICIAL_RULE = "공식 전망 = 지금까지 실현이 확정된 예측의 평균 CRPS가 가장 낮은 모형(A~D). 조건부 모형은 랜덤워크 대비 유의한 개선이 확인되기 전에는 공식 전망에 쓰지 않는다."


def jdump(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def rnd(x, n=2):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


def forecast_at(j, ecos, r, vol, hz, rng, n=40000):
    """원천 데이터 인덱스 j(기준일) 시점의 4개 모형 분포. 반환: {모형: 요약 dict}."""
    base = ecos.index[j]; s0 = float(ecos.iloc[j])
    h = M.horizon_bd(base, hz)
    sig = {"A": vol.sig_A.iloc[j], "B": vol.sig_B.iloc[j], "C": vol.sig_C.iloc[j]}
    pool = M.std_resid_pool(r, vol, j)
    out = {}
    for m in "ABCD":
        smp = None
        if m in "ABC":
            s = sig[m] * np.sqrt(h)
            q = stats.norm.ppf(M.QS) * s
            paths = M.simulate_paths(m, sig, h, pool, 20000, rng)
        else:
            paths = M.simulate_paths("D", sig, h, pool, 20000, rng)
            smp = M.sample_returns("D", sig, h, pool, n, rng)
            q = np.quantile(smp, M.QS)
        out[m] = {"q": q, "paths": paths, "smp": smp, "sig_daily": float(sig["C"] if m == "D" else sig[m]), "h": h, "s0": s0, "base": base}
    return out


def dens_pack(m, d, s0):
    """가격 격자 위의 pdf/cdf. 정규모형은 해석해, D 는 표본(커널밀도·경험분포)."""
    h = d["h"]
    if m in "ABC":
        sg = d["sig_daily"] * np.sqrt(h)
        xs = np.linspace(-4.2 * sg, 4.2 * sg, 241)
        pdf_r = stats.norm.pdf(xs, 0, sg); cdf = stats.norm.cdf(xs, 0, sg)
    else:
        smp = d["smp"]
        lo, hi = np.quantile(smp, [0.0005, 0.9995]); span = hi - lo
        xs = np.linspace(lo - 0.15 * span, hi + 0.15 * span, 241)
        kde = stats.gaussian_kde(smp[::5]); pdf_r = kde(xs)
        cdf = np.searchsorted(np.sort(smp), xs, side="right") / len(smp)
    price = s0 * np.exp(xs)
    pdf_p = pdf_r / price
    return {"price": [rnd(v, 2) for v in price], "pdf": [float(f"{v:.6g}") for v in pdf_p], "cdf": [round(float(v), 5) for v in cdf]}


def barrier_pack(m, d):
    ks = ZERO_GRID[ZERO_GRID != 0]
    sd = d["sig_daily"]
    end, td, tb = M.barrier_curves(d["paths"], sd, ks)
    return {"k": [float(k) for k in ks], "end": [round(float(v), 4) for v in end], "touch_discrete": [round(float(v), 4) for v in td],
            "touch_bridge": [round(float(v), 4) for v in tb]}


def model_card(m, d, bt_sel=None):
    s0 = d["s0"]; q = d["q"]
    pr = s0 * np.exp(q)
    if m == "D":
        pup = float((d["smp"] > 0).mean())
    else:
        pup = 0.5
    return {"median": rnd(pr[3]), "p_up": round(pup, 4), "p_down": round(1 - pup, 4),
            "pi50": [rnd(pr[2]), rnd(pr[4])], "pi80": [rnd(pr[1]), rnd(pr[5])], "pi90": [rnd(pr[0]), rnd(pr[6])],
            "sigma_h_pct": rnd(float(d["sig_daily"] * np.sqrt(d["h"]) * 100), 3) if m != "D" else rnd(float(np.std(d["smp"]) * 100), 3)}


def main(skip_bt=False, write_live=True):
    df = prep.load_long()
    ecos0 = prep.panel_ecos(df)["KRW"].dropna()
    fres = F.compute(df, ecos0.index)
    ecos, r, X = B.build_features(df, fres["panel"]["fpi"])
    rr = r.fillna(0.0)
    vol = M.vol_series(rr)
    dates = ecos.index
    if skip_bt and (DATA / "bt.pkl").exists():
        bt = pd.read_pickle(DATA / "bt.pkl")
    else:
        bt = B.run(df, fpi_series=fres["panel"]["fpi"]); bt.to_pickle(DATA / "bt.pkl")
    rng = np.random.default_rng(20261026)
    j = len(dates) - 1
    base = dates[j]
    spot = float(ecos.iloc[j]); prev = float(ecos.iloc[j - 1])

    # ---------- 최신 전망 ----------
    latest = {"base_date": base.strftime("%Y-%m-%d"), "spot": spot, "prev_close": prev, "prev_date": dates[j - 1].strftime("%Y-%m-%d"),
              "change": rnd(spot - prev), "change_pct": rnd((spot / prev - 1) * 100, 3),
              "definition": "원/미국달러 매매기준율 (한국은행 ECOS 731Y001, 서울외환시장 기준)", "source": "한국은행 경제통계시스템(ECOS)",
              "direction_note": "달러당 원화값 상승 = 원화 약세, 하락 = 원화 강세", "horizons": {}}
    lm = json.loads((DATA / "latest_mu.json").read_text()) if (DATA / "latest_mu.json").exists() else {}
    for hz in (7, 30):
        fc = forecast_at(j, ecos, rr, vol, hz, rng)
        sel = B.default_model_asof(bt, base, hz)
        tdate = base + pd.Timedelta(days=hz)
        latest["horizons"][str(hz)] = {
            "cal_days": hz, "base_date": base.strftime("%Y-%m-%d"), "target_date": tdate.strftime("%Y-%m-%d"), "h_bd": fc["A"]["h"],
            "target_weekday": "토" if tdate.dayofweek == 5 else "일" if tdate.dayofweek == 6 else "",
            "evaluation_rule": "목표일이 휴장일·주말이면 그 이전 마지막 거래일의 매매기준율로 평가", "selected": sel, "selected_name": MODEL_NAMES[sel],
            "experimental_point": {k: (None if lm.get(f"{hz}:{k}") is None else {"mu_pct": rnd(lm[f"{hz}:{k}"] * 100, 3), "value": rnd(spot * float(np.exp(lm[f"{hz}:{k}"])), 1)}) for k in ("E0", "EP")},
            "models": {m: model_card(m, fc[m]) for m in "ABCD"}, "density": {m: dens_pack(m, fc[m], spot) for m in "ABCD"},
            "barrier": {m: barrier_pack(m, fc[m]) for m in "ABCD"}}
    jdump("latest.json", latest)

    # ---------- 시계열 ----------
    ser = ecos[ecos.index >= ecos.index.max() - pd.Timedelta(days=3 * 365 + 5)]
    jdump("series.json", {"dates": [d.strftime("%Y-%m-%d") for d in ser.index], "usdkrw": [rnd(v, 2) for v in ser.values]})

    # ---------- 성적표 ----------
    sc_all = B.scorecard(bt); sc_3y = B.scorecard(bt, since=(base - pd.Timedelta(days=3 * 365)).strftime("%Y-%m-%d"))
    for lst in (sc_all, sc_3y):
        for row in lst:
            row["name"] = MODEL_NAMES[row["model"]]
    live_path = DATA / "live_forecasts.csv"
    live_n = int(len(pd.read_csv(live_path))) if live_path.exists() else 0
    yearly = []
    for (y, hz, m), g in bt[bt.model.isin(list("ABCD"))].groupby([bt.origin.dt.year, "horizon", "model"]):
        yearly.append({"year": int(y), "horizon": int(hz), "model": m, "n": int(len(g)), "crps_pct": rnd(g.crps.mean() * 100, 4)})
    jdump("scorecard.json", {"all": sc_all, "recent3y": sc_3y, "yearly": yearly, "period": [bt.origin.min().strftime("%Y-%m-%d"), bt.origin.max().strftime("%Y-%m-%d")],
                              "live_count": live_n, "rule": OFFICIAL_RULE, "model_names": MODEL_NAMES})

    # ---------- 과거 시점 재현(HISTORICAL MODE): 정보는 기준일까지만 ----------
    hist = {"rule": "과거 자료 재계산: 기준일까지의 환율만으로 다시 계산한 값입니다. 당시 실제로 발표된 전망이 아닙니다.", "origins": []}
    srt = {hz: bt[(bt.horizon == hz) & bt.model.isin(list("ABCD"))] for hz in (7, 30)}
    # 모형별 eval_date 기준 누적 평균 CRPS (as-of 선택용)
    cum = {}
    for hz in (7, 30):
        cum[hz] = {}
        for m in "ABCD":
            g = srt[hz][srt[hz].model == m].sort_values("eval_date")
            cum[hz][m] = (g.eval_date.values, np.cumsum(g.crps.values))
    def sel_asof(hz, asof):
        best, bv = "C", None
        ok = True; vals = {}
        for m in "ABCD":
            ed, cs = cum[hz][m]
            i = np.searchsorted(ed, np.datetime64(asof), side="right")
            if i < 250:
                ok = False; break
            vals[m] = cs[i - 1] / i
        return min(vals, key=vals.get) if ok else "C"
    bt_idx = bt.set_index(["horizon", "model", "origin"]).sort_index()
    cols_start = dates.searchsorted(B.START)
    recent_cut = len(dates) - 45
    for jj in range(cols_start, len(dates), 1):
        d0 = dates[jj]
        entry = {"d": d0.strftime("%Y-%m-%d"), "spot": rnd(float(ecos.iloc[jj]))}
        for hz in (7, 30):
            sel = sel_asof(hz, d0)
            key = (hz, sel, d0)
            if key in bt_idx.index:
                row = bt_idx.loc[key]
                q = [rnd(row.spot * np.exp(row[c])) for c in ("q05", "q10", "q25", "q50", "q75", "q90", "q95")]
                entry[f"h{hz}"] = {"m": sel, "q": q, "pu": rnd(row.p_up, 3), "td": row.eval_date.strftime("%Y-%m-%d"), "real": rnd(row.spot * np.exp(row.y))}
            else:
                if jj >= recent_cut:
                    fc = forecast_at(jj, ecos, rr, vol, hz, np.random.default_rng(jj), n=8000)[sel]
                    pr = fc["s0"] * np.exp(fc["q"])
                    entry[f"h{hz}"] = {"m": sel, "q": [rnd(v) for v in pr], "pu": rnd(model_card(sel, fc)["p_up"], 3), "td": None, "real": None}
        hist["origins"].append(entry)
    jdump("history.json", hist)

    # ---------- 레이더 ----------
    rad = radar.build(df, bt)
    jdump("radar.json", rad)

    # ---------- 실시간 예측 기록(추가만, 덮어쓰기 없음) ----------
    new = []
    exist = pd.read_csv(live_path) if live_path.exists() else pd.DataFrame(columns=["origin"])
    if write_live and base.strftime("%Y-%m-%d") not in set(exist.get("origin", [])):
        for hz in (7, 30):
            h_ = latest["horizons"][str(hz)]; m_ = h_["models"][h_["selected"]]
            new.append({"origin": base.strftime("%Y-%m-%d"), "target_date": h_["target_date"], "horizon": hz, "model": h_["selected"], "spot": spot,
                        "median": m_["median"], "pi50_lo": m_["pi50"][0], "pi50_hi": m_["pi50"][1], "pi80_lo": m_["pi80"][0], "pi80_hi": m_["pi80"][1],
                        "pi90_lo": m_["pi90"][0], "pi90_hi": m_["pi90"][1], "p_up": m_["p_up"], "model_version": "v0.2", "recorded_at": now_kst().isoformat(timespec="seconds")})
        out_df = pd.concat([exist, pd.DataFrame(new)], ignore_index=True)
        out_df["horizon"] = out_df["horizon"].astype(int)
        out_df.to_csv(live_path, index=False)

    # ---------- 다운로드 CSV ----------
    dl = bt.copy()
    for c in ("q05", "q10", "q25", "q50", "q75", "q90", "q95"):
        dl[c] = (dl.spot * np.exp(dl[c])).round(2)
    dl["realized"] = (dl.spot * np.exp(dl.y)).round(2)
    dl = dl.rename(columns={"origin": "forecast_origin", "eval_date": "evaluation_date", "q50": "median", "spot": "spot_at_origin"})
    dl["p_up"] = dl.p_up.round(4); dl["crps_pct"] = (dl.crps * 100).round(4)
    dl["data_type"] = "backtest(walk-forward, 과거 자료 재계산)"
    keep = ["forecast_origin", "target_date", "evaluation_date", "horizon", "model", "spot_at_origin", "median", "q05", "q10", "q25", "q75", "q90", "q95",
            "p_up", "realized", "crps_pct", "data_type"]
    dl[keep].to_csv(OUT / "backtest_forecasts.csv", index=False, encoding="utf-8-sig")
    if live_path.exists():
        (OUT / "live_forecasts.csv").write_bytes(live_path.read_bytes())
    elif (OUT / "live_forecasts.csv").exists():
        (OUT / "live_forecasts.csv").unlink()

    # ---------- FPI / 사건 ----------
    panel = fres["panel"].reindex(ecos.index)
    keep_i = ecos.index >= pd.Timestamp("2012-01-02")
    fh = panel[keep_i]
    ids = [a[0] for a in F.AREAS]
    detail = F.latest_detail(fres, len(ecos) - 1, ecos.index, df)
    jdump("fpi.json", {
        "experimental": True, "label": "실험적 압력 지수 (확률 아님)", "latest": detail, "areas_def": [{"id": a, "name": n, "desc": d} for a, n, d in F.AREAS],
        "weights": "10개 영역 동일가중(각 10%). 자료가 없는 영역은 제외하고 나머지 평균을 쓰며 자료 충족률을 함께 표시",
        "history": {"dates": [d.strftime("%Y-%m-%d") for d in fh.index], "fpi": [rnd(v, 1) for v in fh["fpi"]], "coverage": [rnd(v, 2) for v in fh["coverage"]],
                    **{a: [rnd(v, 1) for v in fh[a]] for a in ids}},
        "validation": F.validate(fres, ecos), "z_window": F.Z_WIN, "signal_window": F.H,
        "sources": {"us_policy": "Yahoo ^FVX·^TNX", "kr_policy": "ECOS 817Y002 국고채 3년", "usd": "Yahoo 6개 통화", "jpy": "Yahoo USD/JPY", "cny": "Yahoo USD/CNY", "twd": "Yahoo USD/TWD",
                    "ext": "ECOS 301Y017 경상수지(월)", "flow": "ECOS 301Y013 증권투자(부채)(월)", "commod": "Yahoo CL=F(WTI)", "market": "Yahoo ^VIX·^KS11"},
        "missing": ["외국인 일별 주식·채권 순매수 자료(월별 국제수지로 대체, 발표 지연)", "지정학 위험 지표", "시장 컨센서스(예상 대비 차이)", "일본은행·인민은행 정책 변수"]})
    evs = EV.build(df)
    jdump("events.json", {"events": evs, "cats": EV.CATS, "note": "공식 통계·시장 데이터에서 규칙으로 추출한 사건입니다. 뉴스·보고서 원문 수집(FX INTELLIGENCE)은 미구현이라 원인과 '예상 대비'는 표시하지 않습니다."})

    # ---------- 메타 ----------
    last = {}
    lng = df.groupby("series").observed_date.max()
    for s_ in ("ecos:KRW_per_USD", "yahoo:USDKRW"):
        last[s_] = lng[s_].strftime("%Y-%m-%d")
    stale_days = (now_kst().date() - base.date()).days
    status = json.loads((DATA / "fetch_status.json").read_text(encoding="utf-8")) if (DATA / "fetch_status.json").exists() else {}
    thresholds = {"ecos:KRW_per_USD": ("한국은행 ECOS 원/달러", 4), "yahoo:USDJPY": ("Yahoo Finance 일봉(비공식)", 4), "yahoo:UST10Y": ("Yahoo Finance 미국 금리·VIX·유가", 4), "ecos:BOP_CURRENT_ACCOUNT": ("ECOS 국제수지(월)", 75)}
    srcs = []
    for s_, (nm, th) in thresholds.items():
        row = df[df.series == s_]
        lo, la = row.observed_date.max(), pd.to_datetime(row.available_at).max()
        age = (now_kst().date() - lo.date()).days
        srcs.append({"series": s_, "name": nm, "last_obs": lo.strftime("%Y-%m-%d"), "last_available": la.strftime("%Y-%m-%d"), "age_days": age, "threshold_days": th, "stale": age > th})
    failed = [k for grp in ("ecos", "yahoo") for k, v_ in (status.get(grp) or {}).items() if isinstance(v_, str) and v_.startswith("fail")]
    jdump("meta.json", {"sources": srcs, "failed_series": failed, "updated_at": now_kst().isoformat(timespec="seconds"), "latest_obs": last, "stale_days": stale_days,
                        "stale_warning": stale_days > 4, "cross_check": prep.cross_check_krw(df), "fetch_status": status,
                        "version": "v0.2.0", "model_names": MODEL_NAMES})
    print("ok", base.date(), len(hist["origins"]))


if __name__ == "__main__":
    main(skip_bt="--skip-bt" in sys.argv, write_live="--no-live" not in sys.argv)
