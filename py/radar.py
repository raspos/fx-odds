"""FX CORRELATION RADAR: 원화와 JPY·CNY·TWD 의 동조화. 모든 계산은 일별 로그수익률(USD 1단위당 외화, 상승=외화 약세) 기준.

자료: Yahoo Finance 일봉 마감(비공식, 무료) 단일 출처. 원·엔·위안·대만 달러와 달러요인 6개 통화가 같은 시각(런던 자정 마감)에 관측돼 시각 불일치가 없고 전 거래일까지 갱신된다.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import grangercausalitytests
import prep
from common import avail_date

CCY = ["JPY", "CNY", "TWD"]
NAMES = {"JPY": "엔화", "CNY": "위안화", "TWD": "대만 달러"}
WINDOWS = (20, 60, 120, 252)
LAGS = (0, 1, 2, 3, 5)
MIN_N = {20: 20, 60: 60, 120: 120, 252: 252}


def returns_Y(df_long):
    p = prep.panel_yahoo_or_fred(df_long, "yahoo")
    r = prep.logret(p.dropna()).copy()
    r["USD_FACTOR"] = prep.dollar_factor(r)
    return r[["KRW"] + CCY + ["USD_FACTOR"]]


def partial_corr(rk, rx, rf):
    """rf 를 통제한 rk, rx 의 부분상관 (윈도우 내 상관행렬 공식)."""
    c = pd.concat([rk, rx, rf], axis=1).corr().values
    rkx, rkf, rxf = c[0, 1], c[0, 2], c[1, 2]
    d = np.sqrt((1 - rkf ** 2) * (1 - rxf ** 2))
    return (rkx - rkf * rxf) / d if d > 0 else np.nan


def rolling_tables(r: pd.DataFrame, win: int):
    """윈도우 win 의 이동 단순상관, 부분상관 (각 CCY)."""
    out = {}
    rk, f = r["KRW"], r["USD_FACTOR"]
    ck_f = rk.rolling(win).corr(f)
    for c in CCY:
        x = r[c]
        ck_x = rk.rolling(win).corr(x)
        cx_f = x.rolling(win).corr(f)
        out[(c, "simple")] = ck_x
        out[(c, "partial")] = (ck_x - ck_f * cx_f) / np.sqrt((1 - ck_f ** 2) * (1 - cx_f ** 2))
    out[("FACTOR", "simple")] = ck_f
    return out


def fisher_ci(rho, n, k=0):
    if n - 3 - k <= 0 or not np.isfinite(rho):
        return (np.nan, np.nan)
    z = np.arctanh(np.clip(rho, -0.999, 0.999)); se = 1 / np.sqrt(n - 3 - k)
    return (float(np.tanh(z - 1.96 * se)), float(np.tanh(z + 1.96 * se)))


def snapshot(r: pd.DataFrame):
    """최신 시점 표: 창별 단순·부분상관, 표본수, 95% 신뢰구간, 21영업일 전 대비 변화."""
    res = {}
    for w in WINDOWS:
        tab = rolling_tables(r, w)
        rows = []
        for c in CCY:
            s, p = tab[(c, "simple")], tab[(c, "partial")]
            s_now, p_now = s.iloc[-1], p.iloc[-1]
            s_prev = s.iloc[-22] if len(s) > 22 else np.nan
            p_prev = p.iloc[-22] if len(p) > 22 else np.nan
            rows.append({"ccy": c, "name": NAMES[c], "simple": _f(s_now), "partial": _f(p_now), "n": w,
                         "simple_ci": [_f(v) for v in fisher_ci(s_now, w)], "partial_ci": [_f(v) for v in fisher_ci(p_now, w, 1)],
                         "simple_chg_1m": _f(s_now - s_prev), "partial_chg_1m": _f(p_now - p_prev)})
        res[str(w)] = {"rows": rows, "krw_vs_factor": _f(tab[("FACTOR", "simple")].iloc[-1])}
    return res


def _f(x, nd=4):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def history(r: pd.DataFrame, since="2016-01-01", avail_src="ecos:KRW_per_USD"):
    d = {"dates": None, "avail": None, "series": {}}
    idx = None
    for w in WINDOWS:
        tab = rolling_tables(r, w)
        for c in CCY:
            for kind in ("simple", "partial"):
                s = tab[(c, kind)]
                s = s[s.index >= since]
                idx = s.index if idx is None else idx
                d["series"][f"{c}_{kind}_{w}"] = [_f(v, 3) for v in s.reindex(idx).values]
    d["dates"] = [x.strftime("%Y-%m-%d") for x in idx]
    # 각 관측이 실제로 확인 가능해진 날(가장 늦게 확정되는 입력 기준). 과거 날짜 선택 시 이 값으로 자른다.
    d["avail"] = [avail_date(avail_src, x).strftime("%Y-%m-%d") for x in idx]
    return d


def scatter(r: pd.DataFrame, win=60):
    t = r.tail(win)
    out = {}
    for c in CCY:
        x, y = t[c].values * 100, t["KRW"].values * 100
        sl, ic, rv, pv, se = stats.linregress(x, y)
        out[c] = {"x": [round(v, 3) for v in x], "y": [round(v, 3) for v in y], "dates": [d.strftime("%Y-%m-%d") for d in t.index],
                  "slope": _f(sl), "intercept": _f(ic), "r": _f(rv), "r2": _f(rv ** 2), "p": _f(pv, 6)}
    return out


def leadlag(r: pd.DataFrame):
    """lag k>=0: corr(KRW_t, X_{t-k})  (X 가 k영업일 앞서는 경우)  /  rev: corr(X_t, KRW_{t-k}) (원화가 앞서는 경우).
    창: 최근 252영업일, 최근 756영업일(약 3년), 756영업일 중 원화 20일 변동성 상위 25% 구간(불안기)과 그 외."""
    out = {}
    vol20 = r["KRW"].rolling(20).std()
    last3 = r.tail(756)
    thr = vol20.loc[last3.index].quantile(0.75)
    stress_flag = (vol20.loc[last3.index] >= thr)
    wins = {"y1": r.tail(252), "y3": last3}
    for c in CCY:
        out[c] = {}
        for wn, w in wins.items():
            out[c][wn] = {"lead": {str(k): _f(_lagcorr(w, "KRW", c, k, r)) for k in LAGS},
                          "rev": {str(k): _f(_lagcorr(w, c, "KRW", k, r)) for k in LAGS if k > 0}}
        # 불안기/평시: 원화 변동성 상위 25% 일자만 골라 같은 계산
        for nm, flag in (("stress", stress_flag), ("calm", ~stress_flag)):
            idxs = flag[flag].index
            out[c][nm] = {"lead": {str(k): _f(_lagcorr_idx(r, "KRW", c, k, idxs)) for k in LAGS},
                          "rev": {str(k): _f(_lagcorr_idx(r, c, "KRW", k, idxs)) for k in LAGS if k > 0}}
    return out


def _lagcorr(w, a, b, k, full):
    """w 구간의 a_t 와 b_{t-k}. b 의 k영업일 전 값은 full 에서 가져온다 (구간 밖 과거 허용, 미래 사용 없음)."""
    x = pd.concat([full[a], full[b].shift(k)], axis=1).loc[w.index].dropna()
    return x.corr().iloc[0, 1] if len(x) > 30 else np.nan


def _lagcorr_idx(full, a, b, k, idxs):
    x = pd.concat([full[a], full[b].shift(k)], axis=1).loc[idxs].dropna()
    return x.corr().iloc[0, 1] if len(x) > 30 else np.nan


def granger(r: pd.DataFrame, maxlag=5, n=756):
    """Granger: X 의 과거가 KRW 예측에 추가 정보를 주는가 (그리고 반대). 경제학적 인과가 아니라 예측정보 검정."""
    out = {}
    t = r.tail(n)
    for c in CCY:
        res = {}
        for name, cols in (("x_to_krw", ["KRW", c]), ("krw_to_x", [c, "KRW"])):
            g = grangercausalitytests(t[cols].dropna().values, maxlag=maxlag)
            res[name] = {str(l): _f(g[l][0]["ssr_ftest"][1], 4) for l in range(1, maxlag + 1)}
            res[name]["min_p"] = min(res[name].values())
        out[c] = res
    return out


def narrative(snap, ll, gr, contrib, win="60") -> list[str]:
    """계산 결과로 규칙 기반 문장을 만든다. LLM 호출 없음."""
    rows = snap[win]["rows"]
    s = sorted(rows, key=lambda x: -(x["simple"] if x["simple"] is not None else -9))
    p = sorted(rows, key=lambda x: -(x["partial"] if x["partial"] is not None else -9))
    out = []
    t1, t2 = s[0], s[1]
    out.append(f"최근 {win}거래일 단순 상관계수는 {t1['name']} {t1['simple']:+.2f}, {t2['name']} {t2['simple']:+.2f}, {s[2]['name']} {s[2]['simple']:+.2f} 순입니다. "
               f"{t1['name']}와의 상관이 가장 높지만, 높은 상관이 {t1['name']}가 원화 환율에 더 큰 영향을 준다는 뜻은 아닙니다.")
    top_p = p[0]
    if top_p["ccy"] != t1["ccy"]:
        out.append(f"글로벌 달러 요인을 통제하면 순위가 바뀝니다: {top_p['name']}(부분상관 {top_p['partial']:+.2f})가 가장 높고, {t1['name']}는 {t1['simple']:+.2f}에서 {t1['partial']:+.2f}로 달라집니다.")
    else:
        d = t1["partial"] - t1["simple"]
        word = "낮아집니다" if d < -0.02 else ("비슷합니다" if abs(d) <= 0.02 else "높아집니다")
        out.append(f"글로벌 달러 요인을 통제해도 {t1['name']}가 가장 높고, 상관은 {t1['simple']:+.2f}에서 {t1['partial']:+.2f}로 {word}.")
    ci = t1["simple_ci"]
    if ci[0] is not None and ci[0] <= 0 <= ci[1]:
        out.append(f"{t1['name']} 상관의 95% 신뢰구간({ci[0]:+.2f}~{ci[1]:+.2f})이 0을 포함해 통계적으로 구별하기 어렵습니다.")
    chg = [r_ for r_ in rows if r_["simple_chg_1m"] is not None]
    if chg:
        m = max(chg, key=lambda r_: abs(r_["simple_chg_1m"]))
        out.append(f"한 달 전과 비교해 가장 크게 변한 것은 {m['name']}로, 상관계수가 {m['simple_chg_1m']:+.2f}포인트 움직였습니다.")
    # 선행성
    msgs = []
    for c in CCY:
        gp = gr[c]["x_to_krw"]["min_p"]
        if gp is not None and gp < 0.05:
            msgs.append(f"{NAMES[c]}(최소 p={gp:.3f})")
    if msgs:
        out.append("Granger 검정에서 " + ", ".join(msgs) + "의 과거 움직임이 원화 수익률 예측에 추가 정보를 보였습니다. 다중검정(3개 통화×5개 시차)을 고려하면 우연일 수 있고, 인과관계를 뜻하지 않습니다.")
    else:
        out.append("Granger 검정에서 세 통화 모두 유의수준 5%에서 원화 수익률 예측에 추가 정보를 주지 못했습니다.")
    # 예측 기여도
    good = [(k, v) for k, v in contrib.items() if v["h30"] is not None and v["h30"]["vs_e0_pct"] > 0 and v["h30"]["p"] < 0.05]
    if good:
        out.append("표본 외 예측에서 " + ", ".join(NAMES.get(k, k) for k, _ in good) + " 추가가 30일 예측 정확도를 통계적으로 유의하게 개선했습니다.")
    else:
        out.append("표본 외 예측(Walk-forward)에서 해당 통화들을 추가해도 원·달러 단독 모형 대비 통계적으로 유의한 개선은 확인되지 않았습니다. 동조화가 크더라도 예측 기여도는 확인되지 않은 상태입니다.")
    return out


def contribution(bt: pd.DataFrame, since="2012-01-01"):
    """조건부 모형(릿지 평균 + EWMA 분산)의 CRPS 를 원·달러 단독 모형(E0)과 비교. HAC DM 검정."""
    import backtest as B
    out = {}
    names = {"EJ": "JPY", "EC": "CNY", "ET": "TWD", "E3": "ALL3", "EF": "ALL3+FACTOR", "EP": "FPI", "ER": "RATES"}
    for k, nm in names.items():
        out[nm] = {}
        for hz in (7, 30):
            a = bt[(bt.horizon == hz) & (bt.model == "E0")].set_index("origin")
            g = bt[(bt.horizon == hz) & (bt.model == k)].set_index("origin")
            com = a.index.intersection(g.index)
            if len(com) < 100:
                out[nm][f"h{hz}"] = None; continue
            d = g.loc[com, "crps"].values - a.loc[com, "crps"].values
            m, t, p = B.nw_dm(d, lag=int(g.h_bd.iloc[0]))
            rmse_e0 = np.sqrt(np.mean(((a.loc[com, "spot"] * (np.exp(a.loc[com, "q50"]) - np.exp(a.loc[com, "y"]))) ** 2)))
            rmse_k = np.sqrt(np.mean(((g.loc[com, "spot"] * (np.exp(g.loc[com, "q50"]) - np.exp(g.loc[com, "y"]))) ** 2)))
            hit = float(((g.loc[com, "mu"] > 0) == (g.loc[com, "y"] > 0)).mean())
            hit0 = float(((a.loc[com, "mu"] > 0) == (a.loc[com, "y"] > 0)).mean())
            out[nm][f"h{hz}"] = {"n": int(len(com)), "crps_e0": _f(a.loc[com, "crps"].mean() * 100), "crps": _f(g.loc[com, "crps"].mean() * 100),
                                 "vs_e0_pct": _f((1 - g.loc[com, "crps"].mean() / a.loc[com, "crps"].mean()) * 100, 3),
                                 "rmse_vs_e0_pct": _f((1 - rmse_k / rmse_e0) * 100, 3), "hit": _f(hit), "hit_e0": _f(hit0), "p": _f(p), "dm_t": _f(t)}
    return out


def build(df_long, bt):
    res = {}
    contrib = contribution(bt)
    for name, fn in (("YAHOO", returns_Y),):
        r = fn(df_long)
        snap = snapshot(r)
        ll = leadlag(r)
        gr = granger(r)
        res[name] = {"last_date": r.index[-1].strftime("%Y-%m-%d"), "n_obs": int(len(r)), "snapshot": snap, "history": history(r, avail_src="yahoo:USDKRW"),
                     "scatter": scatter(r), "leadlag": ll, "granger": gr, "narrative": narrative(snap, ll, gr, contrib)}
    res["contribution"] = contrib
    return res
