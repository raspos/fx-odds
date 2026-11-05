"""일별 지표 스냅샷: 전체 수집 때마다 그날의 주요 지표를 data/snapshots.csv 에 한 줄씩 추가 기록한다(덮어쓰기 없음).
뉴스 압력지수(FSI)는 당시 기사·규칙으로만 만들 수 있어 나중에 복원할 수 없으므로 매일 남겨 추이를 쌓는다.
같은 날 여러 번 기록돼도 화면용 추이(snapshots.json)는 그날 마지막 줄을 쓴다."""
from __future__ import annotations
import csv
from common import DATA, now_kst

PATH = DATA / "snapshots.csv"
COLS = ["recorded_at", "date", "base_date", "spot", "npi", "npi_rule", "n_judged", "n_ai", "fpi", "fpi_coverage", "fxvi", "range_won", "h7_lo", "h7_hi", "h30_lo", "h30_hi", "model_version"]


def record(row: dict) -> None:
    new = not PATH.exists()
    with PATH.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        r = {"recorded_at": now_kst().isoformat(timespec="minutes"), "date": now_kst().date().isoformat(), **row}
        w.writerow(["" if r.get(c) is None else (round(r[c], 2) if isinstance(r[c], float) else r[c]) for c in COLS])


def history() -> dict:
    """날짜별 마지막 기록을 열 단위(배열)로 돌려준다. 빈 값은 None."""
    if not PATH.exists():
        return {"n": 0, "dates": []}
    last: dict = {}
    for r in csv.DictReader(PATH.open(encoding="utf-8")):
        last[r["date"]] = r
    ds = sorted(last)
    def col(c):
        out = []
        for d in ds:
            v = last[d].get(c, "")
            try:
                out.append(float(v))
            except ValueError:
                out.append(None)
        return out
    return {"n": len(ds), "dates": ds, **{c: col(c) for c in COLS[3:-1]}, "base_date": [last[d]["base_date"] for d in ds]}
