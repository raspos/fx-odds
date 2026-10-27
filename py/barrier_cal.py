"""장벽(기간 중 돌파) 확률 보정 검증. 예측 돌파 확률을 실제 고가·저가(ECOS 731Y003) 관측과 비교한다.

정의
- 기준 환율 S0 = 기준일 D 의 매매기준율(전 영업일 세션 D-1 의 거래를 반영). 장벽 = S0 ± 10·20·30원.
- 관측 구간 = 세션 D 부터 '평가일 전 영업일'까지(평가일 T 의 매매기준율은 세션 T-1 까지의 거래를 반영하므로). 이 구간 최고가 >= S0+b, 최저가 <= S0-b 이면 '돌파(접촉)'.
- 예측 = 정규모형의 반사원리 확률(브라운 다리 보정 확률과 같다) 2(1-Φ(|ln((S0±b)/S0)|/(σ√h))), 이산 일별 감시 확률은 Broadie-Glasserman 보정(장벽을 0.5826σ 밀어냄).
한계: 고저가는 은행간 시장의 관측 범위(2024-07 이전 09:00~15:30, 이후 ~02:00)만 담는다. 그 밖의 시간대(새벽·NDF)의 돌파는 관측하지 못하므로
'관측된 돌파 빈도'는 실제 돌파 빈도의 하한이다. 관측 범위가 넓어진 2024-07 이후와 이전을 따로 보고한다.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats
import backtest as B, models as M, vol as V

BAR = (10, 20, 30)
EDGES = [0, 0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.75, 1.0001]
BG = 0.5826
BRK = pd.Timestamp("2024-07-01")


def wilson(k, n, z=1.96):
    if n <= 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    w = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (float(max(0, c - w)), float(min(1, c + w)))


def run(df_long: pd.DataFrame, fpi=None) -> dict:
    ecos, r, X = B.build_features(df_long)
    dates = ecos.index
    vol = M.vol_series(r.fillna(0.0))
    psig = B.park_sigmas(df_long, dates, r)
    v, _ = V.clean(V.ohlc(df_long))
    Hal, Lal = v.H.reindex(dates).values, v.L.reindex(dates).values
    fix = ecos.values
    start_i = dates.searchsorted(B.START)
    T = {}
    for hz in B.HZ:
        t = np.full(len(dates), -1, dtype=int)
        for i, d in enumerate(dates):
            td = M.target_obs(dates, d, hz)
            if td is not None:
                t[i] = dates.get_loc(td)
        T[hz] = t
    rows = []
    for j in range(start_i, len(dates)):
        s0 = fix[j]; base = dates[j]
        for hz in B.HZ:
            tj = T[hz][j]
            if tj <= j:
                continue
            win_h, win_l = Hal[j:tj], Lal[j:tj]           # 세션 D .. 평가일 전 영업일
            if len(win_h) == 0 or np.isnan(win_h).any() or np.isnan(win_l).any():
                continue
            hmax, lmin = win_h.max(), win_l.min()
            h = M.horizon_bd(base, hz)
            for m, sg in (("C", vol.sig_C.iloc[j]), ("P", psig.sig_P.iloc[j])):
                if not np.isfinite(sg) or sg <= 0:
                    continue
                sh = sg * np.sqrt(h)
                for b in BAR:
                    for side in ("up", "down"):
                        lvl = s0 + b if side == "up" else s0 - b
                        bp = abs(np.log(lvl / s0))
                        p_br = 2 * (1 - stats.norm.cdf(bp / sh)); p_ds = 2 * (1 - stats.norm.cdf((bp + BG * sg) / sh)); p_end = 1 - stats.norm.cdf(bp / sh)
                        obs = (hmax >= lvl) if side == "up" else (lmin <= lvl)
                        end_obs = (fix[tj] >= lvl) if side == "up" else (fix[tj] <= lvl)
                        rows.append((base, hz, h, m, b, side, p_br, p_ds, p_end, bool(obs), bool(end_obs)))
    df = pd.DataFrame(rows, columns=["origin", "hz", "h_bd", "model", "b", "side", "p_bridge", "p_disc", "p_end", "obs", "end_obs"])
    # 공통 표본: C 와 P 가 모두 있는 기준일만
    keys = df.groupby("model").origin.apply(set)
    common = keys["C"] & keys["P"]
    df = df[df.origin.isin(common)].copy()
    df["regime"] = np.where(df.origin >= BRK, "post", "pre")
    out = {"n_origins": int(len(common)), "bars_won": list(BAR), "bins": EDGES, "tables": [], "summary": [], "by_bar": []}
    for hz in B.HZ:
        for m in ("C", "P"):
            for reg in ("all", "pre", "post"):
                g = df[(df.hz == hz) & (df.model == m)]
                if reg != "all":
                    g = g[g.regime == reg]
                if len(g) < 200:
                    continue
                h_bd = int(g.h_bd.median())
                bins = pd.cut(g.p_bridge, EDGES, right=False)
                tab = []
                for iv, gg in g.groupby(bins, observed=True):
                    n = len(gg); k = int(gg.obs.sum()); neff = max(1.0, n / h_bd)  # 겹치는 기준일: 독립 표본 수를 h_bd 로 나눠 근사
                    lo, hi = wilson(k / n * neff, neff)
                    tab.append({"lo": float(iv.left), "hi": float(min(1.0, iv.right)), "n": int(n), "n_eff": round(float(neff), 1), "pred_bridge": round(float(gg.p_bridge.mean()), 4),
                                "pred_disc": round(float(gg.p_disc.mean()), 4), "obs": round(float(k / n), 4), "obs_ci": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)]})
                out["tables"].append({"hz": hz, "model": m, "regime": reg, "bins": tab})
                o = g.obs.astype(float)
                out["summary"].append({"hz": hz, "model": m, "regime": reg, "n": int(len(g)), "mean_pred_bridge": round(float(g.p_bridge.mean()), 4), "mean_pred_disc": round(float(g.p_disc.mean()), 4),
                                       "mean_obs": round(float(o.mean()), 4), "brier_bridge": round(float(((g.p_bridge - o) ** 2).mean()), 5), "brier_disc": round(float(((g.p_disc - o) ** 2).mean()), 5),
                                       "brier_end": round(float(((g.p_end - g.end_obs.astype(float)) ** 2).mean()), 5), "mean_end_pred": round(float(g.p_end.mean()), 4), "mean_end_obs": round(float(g.end_obs.mean()), 4)})
                for b in BAR:
                    for side in ("up", "down"):
                        gg = g[(g.b == b) & (g.side == side)]
                        if len(gg):
                            out["by_bar"].append({"hz": hz, "model": m, "regime": reg, "b": b, "side": side, "n": int(len(gg)), "pred": round(float(gg.p_bridge.mean()), 4), "obs": round(float(gg.obs.mean()), 4)})
    out["notes"] = ["관측 구간은 세션 D부터 평가일 전 영업일까지의 은행간 시장 고가·저가이며, 관측 범위 밖(새벽·NDF 등) 돌파는 확인하지 못했으므로 관측 빈도는 실제 돌파 빈도의 하한입니다.",
                    "관측 범위가 2024-07-01에 09:00~15:30에서 ~02:00으로 넓어져 이전·이후를 따로 보고합니다. 2026-07-06 24시간 거래 개시 이후 표본은 아직 적습니다.",
                    "신뢰구간은 겹치는 기준일을 고려해 독립 표본 수를 (표본수÷예측기간 영업일)로 줄인 윌슨 구간입니다."]
    return out
