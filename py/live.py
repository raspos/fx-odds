"""실시간 예측 성적표: 서비스가 공개 시점에 기록해 둔 전망(live_forecasts.csv, 덮어쓰기 없이 추가만)을 실제 환율로 채점한다.
백테스트(과거 자료 재계산)와 분리한다. 평가 규칙: 목표일 당일 또는 그 이전 마지막 거래일의 매매기준율로 판정하고, 아직 그 날이 오지 않았으면 '대기'."""
from __future__ import annotations
import pandas as pd

MIN_EVAL_NOTE = 30  # 이 이상 평가돼야 포함률 해석에 의미가 생긴다(참고 문구용)


def evaluate(live: pd.DataFrame, fix: pd.Series) -> dict:
    """live: 기록 DataFrame, fix: 매매기준율(날짜 인덱스). 반환: JSON 직렬화 가능한 dict."""
    if live is None or len(live) == 0:
        return {"n_total": 0, "n_eval": 0, "by_horizon": [], "recent": [], "since": None, "note_small": True}
    live = live.copy()
    live["target_date"] = pd.to_datetime(live["target_date"]); live["origin"] = pd.to_datetime(live["origin"])
    rows = []
    last_obs = fix.index.max()
    for _, r in live.sort_values(["origin", "horizon"]).iterrows():
        row = {"origin": r.origin.strftime("%Y-%m-%d"), "target_date": r.target_date.strftime("%Y-%m-%d"), "horizon": int(r.horizon), "model": r.model, "spot": float(r.spot),
               "median": float(r["median"]), "pi50": [float(r.pi50_lo), float(r.pi50_hi)], "pi80": [float(r.pi80_lo), float(r.pi80_hi)], "pi90": [float(r.pi90_lo), float(r.pi90_hi)],
               "version": r.model_version, "status": "대기", "realized": None, "eval_date": None}
        if last_obs >= r.target_date:
            ed = fix.index[fix.index.searchsorted(r.target_date, side="right") - 1]
            v = float(fix.loc[ed])
            row.update({"status": "평가", "realized": v, "eval_date": ed.strftime("%Y-%m-%d"),
                        "in50": row["pi50"][0] <= v <= row["pi50"][1], "in80": row["pi80"][0] <= v <= row["pi80"][1], "in90": row["pi90"][0] <= v <= row["pi90"][1],
                        "abs_err": abs(v - row["median"]), "width80": row["pi80"][1] - row["pi80"][0],
                        "side": "구간 안" if row["pi80"][0] <= v <= row["pi80"][1] else ("위로 이탈(원화 약세 쪽)" if v > row["pi80"][1] else "아래로 이탈(원화 강세 쪽)")})
        rows.append(row)
    ev = [r for r in rows if r["status"] == "평가"]
    by = []
    for hz in sorted({r["horizon"] for r in rows}):
        e = [r for r in ev if r["horizon"] == hz]
        n_all = sum(1 for r in rows if r["horizon"] == hz)
        item = {"horizon": hz, "n_recorded": n_all, "n_eval": len(e)}
        if e:
            item.update({"cov50": sum(r["in50"] for r in e) / len(e), "cov80": sum(r["in80"] for r in e) / len(e), "cov90": sum(r["in90"] for r in e) / len(e),
                         "mean_abs_err": sum(r["abs_err"] for r in e) / len(e), "mean_width80": sum(r["width80"] for r in e) / len(e)})
        by.append(item)
    return {"n_total": len(rows), "n_eval": len(ev), "by_horizon": by, "recent": rows[-30:][::-1], "since": rows[0]["origin"] if rows else None, "note_small": len(ev) < MIN_EVAL_NOTE}
