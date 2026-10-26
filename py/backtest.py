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
        "EP": ("+ 압력지수(FPI)", ["FPI"])}


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
    if fpi_series is not None:  # FPI 는 기준일에 이용 가능했던 자료만으로 계산돼 있다(fpi.compute)
        f = fpi_series.reindex(ecos.index)
        X["FPI_5"], X["FPI_20"] = f.rolling(5, min_periods=3).mean(), f.rolling(20, min_periods=10).mean()
    return ecos, r, X


def run(df_long: pd.DataFrame, seed=7, n_paths=3000, fpi_series: pd.Series | None = None):
    ecos, r, X = build_features(df_long, fpi_series)
    dates = ecos.index
    vol = M.vol_series(r.fillna(0.0))
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
        pool = M.std_resid_pool(r.fillna(0.0), vol, j)
        for hz in HZ:
            T, y_arr = tgt[hz]
            if T[j] < 0:
                continue
            h = M.horizon_bd(base, hz); y = float(y_arr[j]); big = BIG[hz]
            res = {}
            for m in "ABCD":
                q, pup, smp = M.dist_summary(m, sig, h, pool, rng, n_paths)
                if m in "ABC":
                    s = sig[m] * np.sqrt(h)
                    crps = float(M.crps_normal(0.0, s, y)); pb = 1 - stats.norm.cdf(big / s)
                else:
                    crps = M.crps_sample(smp, y); pb = float((smp >= big).mean())
                res[m] = (q, pup, crps, pb, 0.0)
            for k in COND:
                mu = mu_hat[(hz, k)][j]
                if not np.isfinite(mu):
                    continue
                s = sig["C"] * np.sqrt(h)
                res[k] = (mu + stats.norm.ppf(M.QS) * s, float(1 - stats.norm.cdf(-mu / s)), float(M.crps_normal(mu, s, y)),
                          float(1 - stats.norm.cdf((big - mu) / s)), mu)
            for m, (q, pup, crps, pb, mu) in res.items():
                rows.append((base, base + pd.Timedelta(days=hz), dates[T[j]], hz, h, m, s0, y, q[0], q[1], q[2], q[3], q[4], q[5], q[6],
                             pup, crps, pb, mu))
    cols = ["origin", "target_date", "eval_date", "horizon", "h_bd", "model", "spot", "y", "q05", "q10", "q25", "q50", "q75", "q90", "q95",
            "p_up", "crps", "p_big_up", "mu"]
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
            directional = m not in "ABCD" and bool(g.p_up.std() > 0.01)  # A~D 는 drift=0 이라 방향 주장이 없다
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


def default_model_asof(bt: pd.DataFrame, asof: pd.Timestamp, hz: int, cands="ABCD") -> str:
    """asof 시점에 이미 실현이 확정된(eval_date<=asof) 예측만으로 평균 CRPS가 가장 낮은 모형. 표본이 부족하면 C."""
    g = bt[(bt.horizon == hz) & (bt.eval_date <= asof) & (bt.model.isin(list(cands)))]
    if len(g) == 0 or g.groupby("model").size().min() < 250:
        return "C"
    return g.groupby("model").crps.mean().idxmin()
