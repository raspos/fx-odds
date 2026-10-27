"""Walk-forward 백테스트. 기준일 t 의 예측은 t 까지 확정된 자료만 사용하고, 조건부 모형의 계수는 목표일이 t 이전인 표본으로만 추정한다."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import models as M
import prep

HZ = (7, 30)
START = pd.Timestamp("2012-01-02")
TRAIN_START = pd.Timestamp("2005-01-03")
BIG = {7: 0.01, 30: 0.02}  # '큰 상승' 이벤트 기준 (로그수익률)
COND = {"E0": ("원·달러만", []), "EJ": ("+ 엔화", ["JPY"]), "EC": ("+ 위안화", ["CNY"]), "ET": ("+ 대만달러", ["TWD"]),
        "E3": ("+ 세 통화", ["JPY", "CNY", "TWD"]), "EF": ("+ 세 통화 + 달러요인", ["JPY", "CNY", "TWD", "USD_FACTOR"]),
        "EP": ("+ 압력지수(FPI)", ["FPI"]),
        "ER": ("+ 세 통화 + 달러요인 + 한미 금리차(F)", ["JPY", "CNY", "TWD", "USD_FACTOR", "SPR"])}


def build_features(df_long: pd.DataFrame, fpi_series: pd.Series | None = None):
    """ECOS 날짜(서울 종가) 기준 설명변수. 해외 통화는 Yahoo 일봉 중 서울 기준일 '이전 영업일까지' 확정된 수익률만 사용."""
    ecos = prep.panel_ecos(df_long)["KRW"].dropna()
    r = np.log(ecos).diff()
    yahoo = prep.logret(prep.panel_yahoo_or_fred(df_long, "yahoo"))
    yahoo["USD_FACTOR"] = prep.dollar_factor(yahoo)
    cal = pd.bdate_range(ecos.index.min(), ecos.index.max())
    X = pd.DataFrame(index=ecos.index)
    for k in (5, 20):
        X[f"KRW_{k}"] = r.rolling(k).sum()
    for c in ("JPY", "CNY", "TWD", "USD_FACTOR"):
        s = yahoo[c].reindex(cal).fillna(0.0).shift(1)  # 서울 기준일 t 에는 t-1 영업일 마감까지만 반영
        for k in (5, 20):
            X[f"{c}_{k}"] = s.rolling(k).sum().reindex(ecos.index)
    # 한미 금리차: 국고채 3년(ECOS, 당일) - 미국 5년(Yahoo, 직전 영업일 마감). 변화량만 사용
    ktb = df_long[df_long.series == "ecos:KTB3Y"].set_index("observed_date").value.reindex(ecos.index).ffill()
    ust = df_long[df_long.series == "yahoo:UST5Y"].set_index("observed_date").value.reindex(cal).ffill().shift(1).reindex(ecos.index).ffill()
    spr = ktb - ust
    X["SPR_5"], X["SPR_20"] = spr.diff(5), spr.diff(20)
    if fpi_series is not None:  # FPI 는 기준일에 이용 가능했던 자료만으로 계산돼 있다(fpi.compute)
        f = fpi_series.reindex(ecos.index)
        X["FPI_5"], X["FPI_20"] = f.rolling(5, min_periods=3).mean(), f.rolling(20, min_periods=10).mean()
    return ecos, r, X


def park_sigmas(df_long: pd.DataFrame, dates: pd.DatetimeIndex, r: pd.Series) -> pd.DataFrame:
    """기준일 j 에 쓸 수 있는 고저가 기반 일 변동성. 매매기준율 FIX(j)는 세션 j-1 을 반영하므로 세션 j-1 의 고저(이용 가능일=j)까지만 쓴다.
    PR = sqrt(최근 20세션 평균 파킨슨 분산), P = PR x sqrt(k), k = 직전 250일 var(FIX 수익률) / 평균 파킨슨 분산(밤사이 갭·관측범위 차이를 걷는 스케일, 기준일까지 자료만)."""
    import vol as V
    v, _ = V.clean(V.ohlc(df_long))
    pv = V.parkinson_var(v.H, v.L).reindex(dates).shift(1)          # 인덱스 j 의 값 = 세션 j-1 분산
    r2 = (r.fillna(0.0) ** 2).where(pv.notna())                      # 인덱스 j 의 수익률 = FIX(j-1)->FIX(j) = 세션 j-1 구간
    m20 = pv.rolling(20, min_periods=15).mean()
    k = r2.rolling(250, min_periods=200).mean() / pv.rolling(250, min_periods=200).mean()
    return pd.DataFrame({"sig_PR": np.sqrt(m20), "sig_P": np.sqrt(k * m20), "k": k}, index=dates)


def run(df_long: pd.DataFrame, seed=7, n_paths=3000, fpi_series: pd.Series | None = None):
    ecos, r, X = build_features(df_long, fpi_series)
    dates = ecos.index
    vol = M.vol_series(r.fillna(0.0))
    psig = park_sigmas(df_long, dates, r)
    sigC = vol.sig_C.values
    spike = np.array([bool(i >= 250 and np.isfinite(sigC[i]) and sigC[i] >= np.nanquantile(sigC[max(0, i - 750):i + 1], 0.8)) for i in range(len(dates))])  # 사전(기준일까지) 정의
    rng = np.random.default_rng(seed)
    start_i = dates.searchsorted(START)
    rows = []

    # ---- 목표값 사전 계산 (표본별 목표 관측일 인덱스 T_i, 로그수익률 y_i)
    tgt = {}
    for hz in HZ:
        T = np.full(len(dates), -1, dtype=int); y = np.full(len(dates), np.nan)
        for i, d in enumerate(dates):
            td = M.target_obs(dates, d, hz)
            if td is not None:
                j = dates.get_loc(td); T[i] = j; y[i] = np.log(ecos.iloc[j] / ecos.iloc[i])
        tgt[hz] = (T, y)

    # ---- 조건부(릿지) 평균 예측: 목표일이 현재 기준일 이전인 표본으로만 21영업일마다 재추정
    mu_hat = {(hz, k): np.full(len(dates), np.nan) for hz in HZ for k in COND}
    train_i0 = dates.searchsorted(TRAIN_START)
    allidx = np.arange(len(dates))
    for hz in HZ:
        T, y = tgt[hz]
        for k, (_, extra) in COND.items():
            cols = ["KRW_5", "KRW_20"] + [f"{c}_{w}" for c in extra for w in (5, 20)]
            Xv = X[cols].values
            ok = np.isfinite(Xv).all(axis=1) & np.isfinite(y)
            last_fit = None; model = None; sc = None
            for j in range(start_i, len(dates)):
                if last_fit is None or j - last_fit >= 21:
                    idx = allidx[(allidx >= train_i0) & (allidx < j) & (T >= 0) & (T <= j) & ok]
                    if len(idx) < 750:
                        continue
                    sc = StandardScaler().fit(Xv[idx])
                    model = Ridge(alpha=float(len(idx))).fit(sc.transform(Xv[idx]), y[idx])
                    last_fit = j
                if model is not None and np.isfinite(Xv[j]).all():
                    mu_hat[(hz, k)][j] = model.predict(sc.transform(Xv[j:j + 1]))[0]

    import json as _j
    from common import DATA as _D
    _j.dump({f"{hz}:{k}": (None if not np.isfinite(mu_hat[(hz, k)][-1]) else float(mu_hat[(hz, k)][-1])) for hz in HZ for k in COND},
            open(_D / "latest_mu.json", "w"))  # 최신 기준일의 조건부(실험) 평균 예측

    # ---- 본 루프
    for j in range(start_i, len(dates)):
        base = dates[j]; s0 = float(ecos.iloc[j])
        sig = {"A": vol.sig_A.iloc[j], "B": vol.sig_B.iloc[j], "C": vol.sig_C.iloc[j]}
        if not np.isfinite(list(sig.values())).all():
            continue
        for pk, col in (("P", "sig_P"), ("PR", "sig_PR")):
            if np.isfinite(psig[col].iloc[j]) and psig[col].iloc[j] > 0:
                sig[pk] = float(psig[col].iloc[j])
        pool = M.std_resid_pool(r.fillna(0.0), vol, j)
        for hz in HZ:
            T, y_arr = tgt[hz]
            if T[j] < 0:
                continue
            h = M.horizon_bd(base, hz); y = float(y_arr[j]); big = BIG[hz]
            res = {}
            for m in ("A", "B", "C", "D", "P", "PR"):
                if m not in sig and m != "D":
                    continue
                q, pup, smp = M.dist_summary(m, sig, h, pool, rng, n_paths)
                if m in M.NORMAL:
                    s = sig[m] * np.sqrt(h)
                    crps = float(M.crps_normal(0.0, s, y)); pb = 1 - stats.norm.cdf(big / s); lg = float(stats.norm.logpdf(y, 0.0, s))
                else:
                    crps = M.crps_sample(smp, y); pb = float((smp >= big).mean())
                    lg = float(np.log(max(stats.gaussian_kde(smp[::4])(y)[0], 1e-12)))  # 표본 밀도(KDE)의 로그
                res[m] = (q, pup, crps, pb, 0.0, lg)
            for k in COND:
                mu = mu_hat[(hz, k)][j]
                if not np.isfinite(mu):
                    continue
                s = sig["C"] * np.sqrt(h)
                res[k] = (mu + stats.norm.ppf(M.QS) * s, float(1 - stats.norm.cdf(-mu / s)), float(M.crps_normal(mu, s, y)),
                          float(1 - stats.norm.cdf((big - mu) / s)), mu, float(stats.norm.logpdf(y, mu, s)))
            for m, (q, pup, crps, pb, mu, lg) in res.items():
                rows.append((base, base + pd.Timedelta(days=hz), dates[T[j]], hz, h, m, s0, y, q[0], q[1], q[2], q[3], q[4], q[5], q[6],
                             pup, crps, pb, mu, lg, bool(spike[j])))
    cols = ["origin", "target_date", "eval_date", "horizon", "h_bd", "model", "spot", "y", "q05", "q10", "q25", "q50", "q75", "q90", "q95",
            "p_up", "crps", "p_big_up", "mu", "logs", "spike"]
    return pd.DataFrame(rows, columns=cols)


def nw_dm(d: np.ndarray, lag: int):
    """손실차이 d 의 평균 = 0 검정 (Newey-West HAC). 평균이 양수면 비교 모형의 손실이 더 크다."""
    n = len(d); m = d.mean(); e = d - m
    v = (e @ e) / n
    for L in range(1, lag + 1):
        w = 1 - L / (lag + 1)
        v += 2 * w * (e[L:] @ e[:-L]) / n
    se = np.sqrt(max(v, 1e-18) / n)
    t = m / se
    return float(m), float(t), float(2 * (1 - stats.norm.cdf(abs(t))))


def scorecard(bt: pd.DataFrame, since: str | None = None) -> list[dict]:
    out = []
    df = bt if since is None else bt[bt.origin >= since]
    for hz in HZ:
        a = df[(df.horizon == hz) & (df.model == "A")].set_index("origin")
        for m, g in df[df.horizon == hz].groupby("model"):
            g = g.set_index("origin")
            sp = g.spot; med = sp * np.exp(g.q50); real = sp * np.exp(g.y)
            err = med - real

            def cov(lo, hi):
                return float(((g.y >= g[lo]) & (g.y <= g[hi])).mean())

            up = (g.y > 0).astype(float)
            bs = float(((g.p_up - up) ** 2).mean())
            bsb = float(((g.p_big_up - (g.y >= BIG[hz]).astype(float)) ** 2).mean())
            directional = m not in ("A", "B", "C", "D", "P", "PR") and bool(g.p_up.std() > 0.01)  # A~D 는 drift=0 이라 방향 주장이 없다
            hit = float(((g.p_up > 0.5) == (g.y > 0)).mean()) if directional else None
            common = a.index.intersection(g.index)
            la, lg = a.loc[common, "crps"].values, g.loc[common, "crps"].values
            dm = nw_dm(lg - la, lag=int(g.h_bd.iloc[0])) if len(common) > 50 and m != "A" else (0.0, 0.0, 1.0)
            ea = (a.loc[common, "spot"] * np.exp(a.loc[common, "q50"]) - a.loc[common, "spot"] * np.exp(a.loc[common, "y"])).values
            out.append({"horizon": hz, "model": m, "n": int(len(g)), "mae": float(err.abs().mean()), "rmse": float(np.sqrt((err ** 2).mean())),
                        "hit": hit, "cov50": cov("q25", "q75"), "cov80": cov("q10", "q90"), "cov90": cov("q05", "q95"),
                        "brier_up": bs, "brier_big_up": bsb, "crps_pct": float(g.crps.mean() * 100),
                        "crps_vs_rw_pct": float((1 - lg.mean() / la.mean()) * 100) if len(common) else None,
                        "rmse_vs_rw_pct": float((1 - np.sqrt((err.loc[common] ** 2).mean()) / np.sqrt((ea ** 2).mean())) * 100) if len(common) else None,
                        "dm_p": dm[2], "dm_dir": "worse" if dm[0] > 0 else "better"})
    return out


CANDS = ("A", "B", "C", "D", "P")  # 공식 후보(PR 은 진단용). 모두 같은 기준일 표본에서만 비교한다


def selection_table(bt: pd.DataFrame, hz: int, cands=CANDS):
    """모든 후보가 예측을 낸 기준일만 남겨 평가일 순으로 누적 CRPS 를 만든다(모형마다 시작 시점이 달라도 공정하게 비교)."""
    g = bt[(bt.horizon == hz) & bt.model.isin(cands)].pivot_table(index=["origin", "eval_date"], columns="model", values="crps")
    g = g.dropna(subset=list(cands)).reset_index().sort_values("eval_date")
    return g["eval_date"].values, {m: np.cumsum(g[m].values) for m in cands}


def select_asof(table, asof) -> str:
    ed, cs = table
    i = int(np.searchsorted(ed, np.datetime64(asof), side="right"))
    if i < 250:
        return "C"
    vals = {m: cs[m][i - 1] / i for m in cs}
    return min(vals, key=vals.get)


def default_model_asof(bt: pd.DataFrame, asof: pd.Timestamp, hz: int, cands=CANDS) -> str:
    """asof 시점에 이미 실현이 확정된(eval_date<=asof) 예측만으로, 모든 후보가 함께 낸 기준일의 평균 CRPS 가 가장 낮은 모형. 표본이 부족하면 C."""
    return select_asof(selection_table(bt, hz, cands), asof)


def vol_comparison(bt: pd.DataFrame) -> list[dict]:
    """변동성 모형(A~D, P, PR)을 같은 기준일 표본에서 비교: CRPS, 구간 포함률, 로그 점수, 랜덤워크·EWMA 대비 개선율. 부분표본: 전체/변동성 급등기/2024-07 전·후."""
    out = []
    ms = ["A", "B", "C", "D", "P", "PR"]
    for hz in HZ:
        g = bt[(bt.horizon == hz) & bt.model.isin(ms)].pivot_table(index="origin", columns="model", values="crps")
        common = g.dropna().index
        meta = bt[(bt.horizon == hz) & (bt.model == "A")].set_index("origin")
        subsets = {"전체": common, "변동성 급등기(사전 정의: 20일 변동성 상위 20%)": common[meta.loc[common, "spike"].values],
                   "2024-07 이전": common[common < pd.Timestamp("2024-07-01")], "2024-07 이후": common[common >= pd.Timestamp("2024-07-01")]}
        for sname, idx in subsets.items():
            if len(idx) < 60:
                continue
            for m in ms:
                x = bt[(bt.horizon == hz) & (bt.model == m)].set_index("origin").loc[idx]
                def cov(lo, hi):
                    return float(((x.y >= x[lo]) & (x.y <= x[hi])).mean())
                c_m = g.loc[idx, m].values
                row = {"horizon": hz, "subset": sname, "model": m, "n": int(len(idx)), "crps_pct": float(c_m.mean() * 100), "logscore": float(x.logs.mean()),
                       "cov50": cov("q25", "q75"), "cov80": cov("q10", "q90"), "cov90": cov("q05", "q95"),
                       "vs_rw_pct": float((1 - c_m.mean() / g.loc[idx, "A"].mean()) * 100), "vs_ewma_pct": float((1 - c_m.mean() / g.loc[idx, "C"].mean()) * 100)}
                if m != "C":
                    dm = nw_dm(c_m - g.loc[idx, "C"].values, lag=int(meta.loc[idx, "h_bd"].iloc[0]))
                    row["dm_p_vs_ewma"] = dm[2]
                out.append(row)
    return out
