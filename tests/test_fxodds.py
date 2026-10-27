import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py"))
import models as M, prep, radar, backtest as B  # noqa: E402

OUT = ROOT / "web" / "public" / "data"
needs_data = pytest.mark.skipif(not (OUT / "latest.json").exists(), reason="build 산출물 없음")


# ---------------- 확률 모형 ----------------
def test_horizon_and_target_rule():
    base = pd.Timestamp("2026-10-26")  # 월요일
    assert M.horizon_bd(base, 7) == 5
    dates = pd.bdate_range("2026-01-01", "2026-12-31")
    # 목표일 토요일 -> 직전 금요일 평가
    assert M.target_obs(dates, pd.Timestamp("2026-10-24") - pd.Timedelta(days=7), 7) == pd.Timestamp("2026-10-23")
    assert M.target_obs(dates[:10], pd.Timestamp("2026-01-05"), 30) is None  # 아직 관측되지 않은 목표


def test_normal_quantiles_nested_and_probabilities():
    s = 0.02
    q = stats.norm.ppf(M.QS) * s
    assert q[0] < q[1] < q[2] < q[3] < q[4] < q[5] < q[6]
    assert (q[5] - q[1]) > (q[4] - q[2]) and (q[6] - q[0]) > (q[5] - q[1])


def test_barrier_matches_reflection_principle_and_exceeds_end():
    rng = np.random.default_rng(1)
    sig, h = 0.004, 5
    paths = M.simulate_paths("B", {"B": sig}, h, None, 150000, rng)
    ks = np.array([0.01, 0.02, -0.01])
    end, td, tb = M.barrier_curves(paths, sig, ks)
    s = sig * np.sqrt(h)
    assert np.all(td >= end - 1e-9)             # 기간 중 돌파 >= 만기 시점
    assert np.all(tb >= td - 1e-9)              # 브라운 다리 보정은 이산 감시보다 크다
    assert np.allclose(tb, 2 * (1 - stats.norm.cdf(np.abs(ks) / s)), atol=0.01)
    assert np.allclose(end[:2], 1 - stats.norm.cdf(ks[:2] / s), atol=0.01)
    assert np.all((end >= 0) & (end <= 1)) and np.all((tb >= 0) & (tb <= 1))


def test_reproducible_with_seed():
    pool = np.random.default_rng(0).standard_normal(1500)
    a = M.sample_returns("D", {"C": 0.004}, 5, pool, 1000, np.random.default_rng(5))
    b = M.sample_returns("D", {"C": 0.004}, 5, pool, 1000, np.random.default_rng(5))
    assert np.array_equal(a, b)


def test_crps_normal_matches_sample_estimator():
    rng = np.random.default_rng(3)
    x = rng.standard_normal(40000) * 0.02
    assert abs(M.crps_sample(x, 0.01) - M.crps_normal(0.0, 0.02, 0.01)) < 2e-4


def test_default_model_uses_only_realised_forecasts():
    n = 300
    idx = pd.bdate_range("2013-01-01", periods=n)
    rows = []
    for m, c in (("A", 3.0), ("B", 2.0), ("C", 1.0), ("D", 2.5), ("P", 1.5)):  # 모든 후보(A~D, P)가 함께 낸 기준일만 비교한다
        for i, d in enumerate(idx):
            rows.append(dict(origin=d, eval_date=d + pd.Timedelta(days=7), horizon=7, model=m, crps=c))
    bt = pd.DataFrame(rows)
    assert B.default_model_asof(bt, idx[-1] + pd.Timedelta(days=30), 7) == "C"
    assert B.default_model_asof(bt, idx[100], 7) == "C"  # 표본 부족 -> 기본값
    # 미래 실현 정보 차단: 어제까지 실현된 것만 센다 (표본이 250 미만이면 폴백)
    assert B.default_model_asof(bt, idx[0], 7) == "C"


def test_nw_dm_detects_mean_shift():
    rng = np.random.default_rng(0)
    d = rng.standard_normal(2000) * 0.1 + 0.05
    assert B.nw_dm(d, 5)[2] < 0.01
    assert B.nw_dm(rng.standard_normal(2000) * 0.1, 5)[2] > 0.01


# ---------------- 환율 데이터 ----------------
@pytest.fixture(scope="module")
def df():
    if not (ROOT / "data" / "fx.sqlite").exists():
        pytest.skip("fx.sqlite 없음")
    return prep.load_long()


def test_direction_unified_usd_per_foreign(df):
    y = prep.panel_yahoo_or_fred(df, "yahoo").dropna()
    # EUR는 'USD per EUR' 원자료를 역수로 바꿔 USD당 외화 방향으로 통일: 1.0~1.0 근방이 아니라 0.7~1.3
    assert 0.5 < y["EUR"].iloc[-1] < 1.5
    assert 800 < y["KRW"].iloc[-1] < 2500 and 50 < y["JPY"].iloc[-1] < 300 and 4 < y["CNY"].iloc[-1] < 10 and 20 < y["TWD"].iloc[-1] < 40


def test_jpy_100yen_unit_not_confused(df):
    e = prep.panel_ecos(df).dropna().iloc[-1]
    implied = e["KRW"] / e["KRW_per_JPY"]  # USD/JPY
    assert 50 < implied < 300           # 100엔 단위 혼동 시 0.5~3 수준이 된다
    assert 3 < e["KRW_per_JPY"] < 20


def test_dollar_factor_sign_and_no_asia():
    idx = pd.bdate_range("2024-01-01", periods=5)
    ret = pd.DataFrame({c: 0.01 for c in prep.FACTOR_CCY}, index=idx)
    ret["KRW"] = -0.5  # 한국 원은 요인에 들어가면 안 된다
    f = prep.dollar_factor(ret)
    assert np.allclose(f, 0.01)          # 달러 강세 = +
    assert not set(prep.ASIA) & set(prep.FACTOR_CCY)


def test_no_nonpositive_or_weekend_rows(df):
    assert (df.value > 0).all()
    daily = df[~df.series.str.contains("BOP_|POLICY_|FLOW_")]  # 월별 국제수지는 월말 관측일
    assert (daily.observed_date.dt.dayofweek < 5).all()


# ---------------- 동조화 ----------------
def test_partial_corr_equals_residual_corr():
    rng = np.random.default_rng(2)
    f = pd.Series(rng.standard_normal(500))
    k = 0.6 * f + rng.standard_normal(500); x = 0.5 * f + 0.3 * k + rng.standard_normal(500)
    pc = radar.partial_corr(k, x, f)
    rk = k - np.polyval(np.polyfit(f, k, 1), f); rx = x - np.polyval(np.polyfit(f, x, 1), f)
    assert abs(pc - np.corrcoef(rk, rx)[0, 1]) < 1e-9


def test_rolling_corr_has_no_lookahead():
    rng = np.random.default_rng(4)
    idx = pd.bdate_range("2020-01-01", periods=400)
    r = pd.DataFrame(rng.standard_normal((400, 5)) * 0.005, index=idx, columns=["KRW", "JPY", "CNY", "TWD", "USD_FACTOR"])
    full = radar.rolling_tables(r, 60)[("JPY", "partial")]
    cut = radar.rolling_tables(r.iloc[:300], 60)[("JPY", "partial")]
    assert np.allclose(full.iloc[:300].dropna(), cut.dropna())
    # 미래 값을 바꿔도 과거 상관은 변하지 않는다
    r2 = r.copy(); r2.iloc[350:, 1] = 9.0
    assert np.allclose(radar.rolling_tables(r2, 60)[("JPY", "partial")].iloc[:340].dropna(), full.iloc[:340].dropna())


def test_returns_not_levels(df):
    r = radar.returns_Y(df)
    assert r["KRW"].abs().max() < 0.2  # 가격 수준(1,300)이 아니라 일별 로그수익률


def test_lead_lag_uses_only_past_values():
    rng = np.random.default_rng(6)
    idx = pd.bdate_range("2020-01-01", periods=800)
    x = pd.Series(rng.standard_normal(800), index=idx)
    k = 0.8 * x.shift(2).fillna(0) + 0.3 * rng.standard_normal(800)  # X 가 2일 앞섬
    r = pd.DataFrame({"KRW": k, "JPY": x, "CNY": rng.standard_normal(800), "TWD": rng.standard_normal(800), "USD_FACTOR": rng.standard_normal(800)}, index=idx)
    ll = radar.leadlag(r)
    lead = ll["JPY"]["y3"]["lead"]
    assert lead["2"] > 0.5 and abs(lead["1"]) < 0.2


# ---------------- 산출물 ----------------
@needs_data
def test_latest_json_probability_integrity():
    L = json.loads((OUT / "latest.json").read_text(encoding="utf-8"))
    for hz in ("7", "30"):
        H = L["horizons"][hz]
        for m, c in H["models"].items():
            assert 0 <= c["p_up"] <= 1 and abs(c["p_up"] + c["p_down"] - 1) < 1e-9
            assert c["pi90"][0] <= c["pi80"][0] <= c["pi50"][0] <= c["median"] <= c["pi50"][1] <= c["pi80"][1] <= c["pi90"][1]
            dn = H["density"][m]
            cdf = np.array(dn["cdf"]); price = np.array(dn["price"])
            assert np.all(np.diff(cdf) >= -1e-12) and cdf[0] < 0.05 and cdf[-1] > 0.95 and np.all(np.diff(price) > 0)
            area = np.trapezoid(np.array(dn["pdf"]), price)
            assert 0.9 < area < 1.05
            b = H["barrier"][m]
            assert all(0 <= v <= 1 for v in b["end"] + b["touch_discrete"] + b["touch_bridge"])
            assert all(t >= e - 0.02 for t, e in zip(b["touch_bridge"], b["end"]))  # 기간 중 돌파 >= 만기 확률 (표본오차 허용)


@needs_data
def test_scorecard_and_sources_present():
    S = json.loads((OUT / "scorecard.json").read_text(encoding="utf-8"))
    assert S["all"] and all(0 <= r["cov90"] <= 1 for r in S["all"])
    M_ = json.loads((OUT / "meta.json").read_text(encoding="utf-8"))
    assert M_["latest_obs"]["ecos:KRW_per_USD"] and M_["updated_at"]


# ---------------- 이용 가능 시각 / FPI ----------------
def test_availability_rules():
    from common import avail_date
    d = pd.Timestamp("2026-10-16")  # 금요일
    assert avail_date("ecos:KRW_per_USD", d) == d
    assert avail_date("yahoo:USDJPY", d) == d + pd.Timedelta(days=1)
    assert avail_date("fred:USDJPY", d) == pd.Timestamp("2026-10-19")  # H.10: 다음 월요일
    assert avail_date("fred:DGS2", d) == pd.Timestamp("2026-10-19")
    assert avail_date("ecos:BOP_CURRENT_ACCOUNT", pd.Timestamp("2026-08-31")) > pd.Timestamp("2026-09-30")


@needs_data
def test_historical_radar_never_uses_unavailable_observations():
    R = json.loads((OUT / "radar.json").read_text(encoding="utf-8"))
    for v in ("YAHOO",):
        h = R[v]["history"]
        assert all(a >= d for a, d in zip(h["avail"], h["dates"]))
        assert h["avail"] == sorted(h["avail"])  # 선택일로 자를 수 있도록 단조
    h = R["YAHOO"]["history"]
    asof = "2025-03-14"
    last = max(i for i, a in enumerate(h["avail"]) if a <= asof)
    assert h["dates"][last] <= asof and h["avail"][last] <= asof


def test_fpi_uses_only_available_inputs():
    import fpi
    idx = pd.bdate_range("2024-01-01", periods=10)
    df = pd.DataFrame({"series": "fred:DGS2", "observed_date": idx, "value": np.arange(10.0) + 1})
    df["available_at"] = [(d + pd.offsets.BDay(1)).strftime("%Y-%m-%d") for d in idx]
    v, o = fpi.asof_series(df, "fred:DGS2", idx)
    assert np.isnan(v.iloc[0])                      # 첫날엔 아직 공개된 값이 없다
    assert (o.dropna() < idx[1:][: len(o.dropna())]).all()  # 관측일 < 기준일
    assert v.iloc[3] == 3.0                         # 기준일 D 에는 D-1 값


@needs_data
def test_fpi_range_and_coverage():
    F = json.loads((OUT / "fpi.json").read_text(encoding="utf-8"))
    vals = [v for v in F["history"]["fpi"] if v is not None]
    assert vals and -100 <= min(vals) and max(vals) <= 100
    assert all(0 <= c <= 1 for c in F["history"]["coverage"])
    assert F["experimental"] is True


def test_dxy_aligned_with_own_dollar_factor(df):
    import radar
    if not (df.series == "yahoo:DXY").any():
        pytest.skip("DXY 미수집 DB(다음 전체 수집에서 채워짐)")
    r = radar.returns_Y(df).dropna().tail(500)
    assert r["USD_FACTOR"].corr(r["DXY"]) > 0.6  # 날짜 정렬이 맞으면 달러 요인과 DXY 는 강하게 같이 움직인다


def test_daily_runner_modules_import():
    """CI 의존성 누락(예: yaml)을 테스트 단계에서 잡는다."""
    import importlib
    for m in ("run_daily", "build", "news", "ai_news", "reports", "fetch", "fpi", "events"):
        importlib.import_module(m)


def test_institution_names_are_unified():
    import reports
    for raw in ("신한證", "한투證", "한투증권", "한국투자증권", "유진證", "하나證"):
        assert reports.canon_institution(raw).endswith(("증권",)), raw
    assert reports.canon_institution("한투證") == reports.canon_institution("한투증권") == "한국투자증권"
    assert reports.canon_institution("신한證") == "신한투자증권"


# ---------------- FX VOLATILITY ----------------
@pytest.fixture(scope="module")
def ohlc_df(df):
    import vol
    if not (df.series == "ecos:OHLC_HIGH").any():
        pytest.skip("OHLC 미수집 DB")
    return vol.ohlc(df)


def test_ohlc_columns_selected_by_name_not_position(ohlc_df):
    import vol
    last = ohlc_df.dropna(subset=["H", "L"]).iloc[-1]
    assert last.H >= last.L and last.H > 500 and last.FIX > 500  # 고가가 저가보다 높고 모두 원/달러 수준


def test_ohlc_consistency_after_cleaning(ohlc_df):
    import vol
    v, dropped = vol.clean(ohlc_df)
    assert (v.H >= v[["O", "C"]].max(axis=1)).all() and (v.L <= v[["O", "C"]].min(axis=1)).all() and (v.H >= v.L).all()
    assert len(dropped) <= 5  # 2001·2002년 원자료 오류 2건만 제외


def test_parkinson_formula_against_synthetic_case():
    import vol
    h, l = pd.Series([102.0]), pd.Series([100.0])
    assert abs(vol.parkinson_var(h, l).iloc[0] - np.log(1.02) ** 2 / (4 * np.log(2))) < 1e-12
    # 알려진 상수 변동성의 표본: 일 σ=1% 로 만든 브라운 경로의 고저로 추정하면 σ 근처
    rng = np.random.default_rng(0)
    steps = rng.standard_normal((4000, 400)) * 0.01 / 20       # 일을 400구간으로 쪼갠 경로
    path = np.cumsum(steps, axis=1)
    H, L = 100 * np.exp(path.max(axis=1).clip(min=0)), 100 * np.exp(path.min(axis=1).clip(max=0))
    est = np.sqrt(vol.parkinson_var(pd.Series(H), pd.Series(L)).mean())
    assert 0.0085 < est < 0.0105


def test_fxvi_range_and_insufficient_history_is_nan():
    import vol
    idx = pd.bdate_range("2024-07-01", periods=300)
    m = pd.DataFrame({"park20_daily": np.linspace(0.004, 0.009, 300)}, index=idx)
    f = vol.fxvi(m, [pd.Timestamp("2024-07-01")])
    assert f.dropna().between(0, 100).all()
    assert f.iloc[:200].isna().all()             # 같은 구간 252거래일이 안 쌓이면 산출하지 않는다
    assert f.dropna().iloc[-1] > 95              # 계속 오르는 변동성은 백분위가 매우 높다


def test_ohlc_available_after_observation(df):
    g = df[df.series == "ecos:OHLC_HIGH"]
    if g.empty:
        pytest.skip("OHLC 미수집 DB")
    assert (pd.to_datetime(g.available_at) > g.observed_date).all()   # 세션 종료 후에야 확정


def test_p_model_is_normal_not_bootstrap_branch():
    import models as Mo
    assert "P" in Mo.NORMAL and "PR" in Mo.NORMAL and "D" not in Mo.NORMAL
    rng = np.random.default_rng(1)
    x = Mo.sample_returns("P", {"P": 0.004, "C": 0.004}, 5, np.zeros(10), 20000, rng)
    assert abs(x.std() - 0.004 * np.sqrt(5)) < 0.0005         # 정규 표본(σ√h), 재표본추출 분기로 빠지지 않음


@needs_data
def test_barrier_window_starts_at_origin_session_and_outputs_sane():
    import json
    Bc = json.loads((OUT / "barrier.json").read_text(encoding="utf-8"))
    assert Bc["n_origins"] > 1000
    for t in Bc["tables"]:
        for b in t["bins"]:
            assert 0 <= b["obs"] <= 1 and 0 <= b["pred_bridge"] <= 1 and b["pred_disc"] <= b["pred_bridge"] + 1e-9  # 이산 감시는 보정값보다 작다
    for s_ in Bc["summary"]:
        assert s_["mean_end_pred"] <= s_["mean_pred_bridge"] + 1e-9    # 만기 시점 확률 <= 기간 중 돌파 확률


@needs_data
def test_vol_json_integrity():
    import json
    V = json.loads((OUT / "vol.json").read_text(encoding="utf-8"))
    L = V["latest"]
    assert L["H"] >= L["L"] and L["range_won"] == round(L["H"] - L["L"], 1)
    assert L["fxvi"] is None or 0 <= L["fxvi"] <= 100
    assert V["asof"] < V["available_at"]
