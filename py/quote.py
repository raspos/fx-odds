"""시장 호가(참고) 한 줄 수집: Yahoo Finance KRW=X 최근 호가. 비공식·지연 시세이며 전망의 기준값(ECOS 매매기준율)과 다르다.
출력: JSON 한 줄(stdout) 또는 파일. 실패하면 종료코드 1(기존 값을 덮어쓰지 않도록)."""
import json, sys, time
from datetime import datetime, timedelta, timezone
import requests

KST = timezone(timedelta(hours=9))


def fetch() -> dict:
    last = None
    for host in ("query2", "query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/KRW=X", params={"range": "1d", "interval": "5m"},
                             headers={"User-Agent": "Mozilla/5.0 (fx-odds quote)"}, timeout=30)
            if r.status_code != 200:
                last = r.status_code; time.sleep(3); continue
            m = r.json()["chart"]["result"][0]["meta"]
            price, t = float(m["regularMarketPrice"]), int(m["regularMarketTime"])
            if not (800 < price < 2500):
                raise ValueError("범위 밖")
            tk = datetime.fromtimestamp(t, KST)
            return {"price": round(price, 2), "time": tk.isoformat(timespec="minutes"), "source": "Yahoo Finance KRW=X(비공식·지연)",
                    "fetched": datetime.now(KST).isoformat(timespec="minutes")}
        except Exception as e:
            last = type(e).__name__; time.sleep(3)
    raise SystemExit(f"quote 실패: {last}")


if __name__ == "__main__":
    q = fetch()
    out = sys.argv[1] if len(sys.argv) > 1 else None
    s = json.dumps(q, ensure_ascii=False)
    if out:
        open(out, "w", encoding="utf-8").write(s)
    print(s)
