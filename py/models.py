"""USD/KRW 확률 예측 모형 A~D, 장벽(기간 중 돌파) 확률, 점수 함수.

모든 모형은 일별 로그수익률 r_t = ln(S_t/S_{t-1}) 의 h영업일 합으로 만기 로그수익률 분포를 만든다 (drift=0 가정).
 A 랜덤워크      : 중앙값=현재값, 변동성=전체 역사 표준편차(장기 고정 분산)
 B 역사적 변동성 : 최근 252영업일 표준편차, 정규분포
 C EWMA          : λ=0.94 지수가중 분산, 정규분포
 D FHS 재표본    : EWMA로 표준화한 과거 잔차(최근 1,500일)를 복원추출해 h일 합산, 현재 EWMA 변동성으로 재척도 (두꺼운 꼬리 반영)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats

LAMBDA = 0.94
WIN_B = 252
POOL_D = 1500
QS = np.array([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
MODELS = {"A": "랜덤워크(장기변동성)", "B": "역사적 변동성", "C": "EWMA", "D": "역사적 재표본추출(FHS)", "P": "파킨슨(고저가, 스케일 보정)", "PR": "파킨슨(원시, 참고)"}
NORMAL = {"A", "B", "C", "P", "PR"}   # 정규분포 모형. 나머지(D)는 재표본추출. 문자열 포함 검사(in "ABC")를 쓰지 않는다


def horizon_bd(base: pd.Timestamp, cal_days: int) -> int:
    """기준일부터 목표일(기준일+달력일)까지의 평일 수. 7일→5, 30일→21~22."""
    t = base + pd.Timedelta(days=cal_days)
    return int(np.busday_count(base.date(), t.date()))


def target_obs(dates: pd.DatetimeIndex, base: pd.Timestamp, cal_days: int):
    """평가 규칙: 목표일(기준일+달력일) 당일 또는 그 이전 마지막 관측 거래일의 환율. 아직 관측이 없으면 None."""
    t = base + pd.Timedelta(days=cal_days)
    if dates[-1] < t:
        return None
    i = dates.searchsorted(t, side="right") - 1
    return dates[i]


def vol_series(r: pd.Series) -> pd.DataFrame:
    """각 시점 t 까지의 정보로 계산한 일별 변동성 추정치 (미래정보 없음)."""
    x = r.values
    n = len(x)
    ew = np.empty(n)
    v = np.var(x[:60]) if n > 60 else np.var(x)
    for i in range(n):
        v = LAMBDA * v + (1 - LAMBDA) * x[i] ** 2
        ew[i] = np.sqrt(v)
    expanding = np.sqrt(pd.Series(x).expanding(min_periods=250).apply(lambda a: np.mean(a ** 2), raw=True).values)
    roll = pd.Series(x).rolling(WIN_B, min_periods=WIN_B).std().values
    return pd.DataFrame({"sig_A": expanding, "sig_B": roll, "sig_C": ew}, index=r.index)


def std_resid_pool(r: pd.Series, vol: pd.DataFrame, upto: int) -> np.ndarray:
    """upto(포함)까지의 표준화 잔차 풀. z_t = r_t / sigma_C,t-1."""
    s = vol["sig_C"].shift(1).values
    z = (r.values / s)[: upto + 1]
    z = z[np.isfinite(z)][-POOL_D:]
    return z - z.mean()


def sample_returns(model: str, sig_d: dict, h: int, pool: np.ndarray, n: int, rng) -> np.ndarray:
    """h영업일 합 로그수익률 표본 (n개)."""
    if model in NORMAL:
        return rng.standard_normal(n) * sig_d[model] * np.sqrt(h)
    idx = rng.integers(0, len(pool), size=(n, h))
    return pool[idx].sum(axis=1) * sig_d["C"]


def dist_summary(model: str, sig_d: dict, h: int, pool: np.ndarray | None, rng, n=4000):
    """분위수(로그수익률), 상승확률, 표본(D 전용)."""
    if model in NORMAL:
        s = sig_d[model] * np.sqrt(h)
        return stats.norm.ppf(QS) * s, 0.5, None
    x = sample_returns("D", sig_d, h, pool, n, rng)
    return np.quantile(x, QS), float((x > 0).mean()), x


def crps_normal(mu, sigma, y):
    z = (y - mu) / sigma
    return sigma * (z * (2 * stats.norm.cdf(z) - 1) + 2 * stats.norm.pdf(z) - 1 / np.sqrt(np.pi))


def crps_sample(x: np.ndarray, y: float) -> float:
    xs = np.sort(x)
    n = len(xs)
    term1 = np.mean(np.abs(xs - y))
    i = np.arange(1, n + 1)
    term2 = np.sum((2 * i - n - 1) * xs) / (n * n)
    return float(term1 - term2)


# ---- 장벽(기간 중 돌파) 확률 -----------------------------------------------------------------
def simulate_paths(model: str, sig_d: dict, h: int, pool, n: int, rng) -> np.ndarray:
    """누적 로그수익률 경로 (n, h). 일별 이산 관측."""
    if model in NORMAL:
        steps = rng.standard_normal((n, h)) * sig_d[model]
    else:
        steps = pool[rng.integers(0, len(pool), size=(n, h))] * sig_d["C"]
    return np.cumsum(steps, axis=1)


def barrier_curves(paths: np.ndarray, sigma_daily: float | None, ks: np.ndarray):
    """ks: 로그 임계 수준 (현재 대비). 위쪽 임계(k>0)는 경로 최대값, 아래쪽(k<0)은 최소값으로 판정.
    반환: end(만기 시점 P(R_h>=k) 또는 P(R_h<=k)), touch_discrete, touch_bridge (정규모형만)."""
    n, h = paths.shape
    end = paths[:, -1]
    mx, mn = paths.max(axis=1), paths.min(axis=1)
    out_end, out_td, out_tb = [], [], []
    full = np.concatenate([np.zeros((n, 1)), paths], axis=1)
    for k in ks:
        if k >= 0:
            out_end.append(float((end >= k).mean())); out_td.append(float((mx >= k).mean()))
        else:
            out_end.append(float((end <= k).mean())); out_td.append(float((mn <= k).mean()))
        if sigma_daily:
            a, b = full[:, :-1], full[:, 1:]
            if k >= 0:
                hit = (full.max(axis=1) >= k)
                p_cross = np.exp(-2 * np.clip(k - a, 0, None) * np.clip(k - b, 0, None) / sigma_daily ** 2)
                p_cross = np.where((a >= k) | (b >= k), 1.0, p_cross)
            else:
                hit = (full.min(axis=1) <= k)
                p_cross = np.exp(-2 * np.clip(a - k, 0, None) * np.clip(b - k, 0, None) / sigma_daily ** 2)
                p_cross = np.where((a <= k) | (b <= k), 1.0, p_cross)
            out_tb.append(float(1 - np.prod(1 - p_cross, axis=1).mean()))
    return np.array(out_end), np.array(out_td), (np.array(out_tb) if sigma_daily else None)
