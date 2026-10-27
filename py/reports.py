"""증권사·금융기관 환율 전망 보고서 목록(BOK워치의 '보고서 전망'과 같은 형식).

원문 보고서는 대부분 유료·비공개라 수집하지 않는다. 언론 보도 제목(네이버 뉴스 API로 이미 수집한 제목·링크)에서
기관명·전망 수준·시점을 AI 로 추출하고 모두 '언론 보도 인용(원문 미확인)'으로 표시한다. 같은 기관은 최신 보도만 컨센서스에 넣는다.
수기 입력: data/reports_manual.yaml (BOK워치 reports.yaml 과 같은 방식, verify=false 로 원문 확인 표시 가능).
"""
from __future__ import annotations
import json, os, re
from datetime import timedelta
import requests
import yaml
from common import DATA, now_kst, redact
import news

CACHE = DATA / "fx_reports.jsonl"
MANUAL = DATA / "reports_manual.yaml"
MODEL = os.environ.get("FXODDS_AI_MODEL", "gpt-5.4-mini-2026-03-17")
BATCH = 20
MAX_PER_RUN = 120

INST = re.compile(r"證|증권|은행|리서치|연구원|연구소|KB|신한|하나|우리|NH|삼성|한투|키움|메리츠|대신|유진|iM|IBK|BNK|DB금융|DS투자|상상인|한화투자|현대차|SK|LS|IMF|OECD|골드만|JP\s?모건|모건스탠리|씨티|UBS|BoA|바클레이|노무라|HSBC|도이치|BNP|SC제일|웰스파고|맥쿼리|무디스|S&P|피치|ING|MUFG|커먼즈뱅크|코메르츠|맥쿼리|웰스파고|DBS|OCBC|다이와|미즈호|BMO|RBC|TD증권|소시에테|크레디트스위스|ANZ|웨스트팩")
FORECAST = re.compile(r"전망|예상|관측|내다|제시|예측|상향|하향|목표|내년|연말|분기|연평균|1,?\d{3}원")
FX = re.compile(r"환율|달러[-/·]?\s*원|원\s*[/·-]\s*달러|원화")

SYSTEM = """당신은 한국 원/달러 환율 전망 기사 제목에서 정보를 뽑는 추출기다. 입력은 제목뿐이다.
각 제목이 '특정 금융기관·증권사·연구소의 원/달러 환율(달러-원) 전망'을 전하면 is_forecast=true.
- institution: 제목에 나온 기관명(예: 신한투자증권, 하나증권, 골드만삭스). 없으면 빈 문자열.
- horizon: 전망 시점 표현(예: 연말, 내년 평균, 3분기, 1분기 말, 단기). 없으면 빈 문자열.
- level_low/level_high: 제목에 나온 원/달러 전망 수준(원). 하나면 둘에 같은 값, 없으면 0.
- view: krw_weak(환율 상승·원화 약세 전망), krw_strong(환율 하락·원화 강세 전망), range(박스권·횡보), none(제목에서 알 수 없음).
- summary: 제목 근거만으로 40자 이내 한 문장. 제목에 없는 내용은 쓰지 마라. 추정 금지.
is_forecast=false 이면 나머지는 빈 값/0/none."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["id", "is_forecast", "institution", "horizon", "level_low", "level_high", "view", "summary"],
    "properties": {"id": {"type": "string"}, "is_forecast": {"type": "boolean"}, "institution": {"type": "string"}, "horizon": {"type": "string"},
                   "level_low": {"type": "integer"}, "level_high": {"type": "integer"}, "view": {"type": "string", "enum": ["krw_weak", "krw_strong", "range", "none"]},
                   "summary": {"type": "string"}}}}}}


def load_cache() -> dict:
    out = {}
    if CACHE.exists():
        for l in CACHE.read_text(encoding="utf-8").splitlines():
            if l.strip():
                r = json.loads(l); out[r["id"]] = r
    return out


def candidates():
    for it in news.load():
        t = it["title"]
        if not it.get("official") and FX.search(t) and FORECAST.search(t) and INST.search(t):
            yield it


def extract() -> dict:
    if not os.environ.get("OPENAI_API_KEY"):
        return {"ok": False, "why": "OPENAI_API_KEY 없음"}
    cache = load_cache()
    todo = [i for i in candidates() if i["id"] not in cache][:MAX_PER_RUN]
    if not todo:
        return {"ok": True, "added": 0}
    rows, err = [], None
    try:
        for k in range(0, len(todo), BATCH):
            b = todo[k:k + BATCH]
            user = "다음 제목들을 처리하라. id 를 그대로 돌려줘라.\n" + "\n".join(f"{x['id']}\t{x['title']}" for x in b)
            body = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], "max_completion_tokens": 6000,
                    "reasoning_effort": "medium", "response_format": {"type": "json_schema", "json_schema": {"name": "fx_reports", "strict": True, "schema": SCHEMA}}}
            r = requests.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}, json=body, timeout=180)
            r.raise_for_status()
            ch = r.json()["choices"][0]
            if ch.get("finish_reason") == "length":
                raise RuntimeError("출력 한도 초과")
            ids = {x["id"] for x in b}
            rows += [{**x, "model": MODEL, "at": now_kst().isoformat(timespec="minutes")} for x in json.loads(ch["message"]["content"])["items"] if x["id"] in ids]
    except Exception as e:
        err = redact(type(e).__name__ + " " + str(e))[:160]
    if rows:
        with CACHE.open("a", encoding="utf-8") as f:
            for r_ in rows:
                f.write(json.dumps(r_, ensure_ascii=False) + "\n")
    return {"ok": err is None, "added": len(rows), **({"why": err} if err else {})}


CANON = [  # (정규식, 표준 기관명) — 위에서부터 먼저 맞는 것을 쓴다. '證' 같은 약칭과 '증권'/'투자증권' 표기를 통일한다
    (r"한국?투자|한투", "한국투자증권"), (r"신한", "신한투자증권"), (r"유진", "유진투자증권"), (r"미래에셋", "미래에셋증권"), (r"삼성증권|삼성證|^삼성$", "삼성증권"),
    (r"KB", "KB증권"), (r"NH", "NH투자증권"), (r"키움", "키움증권"), (r"대신", "대신증권"), (r"메리츠", "메리츠증권"), (r"하나", "하나증권"),
    (r"현대차", "현대차증권"), (r"한화", "한화투자증권"), (r"우리", "우리투자증권"), (r"IBK", "IBK투자증권"), (r"iM|아이엠", "iM증권"), (r"하이투자", "하이투자증권"),
    (r"DB", "DB금융투자"), (r"교보", "교보증권"), (r"SK", "SK증권"), (r"유안타", "유안타증권"), (r"상상인", "상상인증권"), (r"BNK", "BNK투자증권"),
    (r"골드만", "골드만삭스"), (r"JP\s?모건|제이피모건", "JP모건"), (r"모건스탠리", "모건스탠리"), (r"씨티", "씨티그룹"), (r"UBS", "UBS"), (r"BoA|뱅크오브아메리카", "뱅크오브아메리카"),
    (r"바클레이", "바클레이스"), (r"노무라", "노무라"), (r"HSBC", "HSBC"), (r"도이치", "도이치뱅크"), (r"SC제일", "SC제일은행"), (r"IMF", "IMF"), (r"OECD", "OECD"),
]


def canon_institution(name: str) -> str:
    n = re.sub(r"\s+", "", name or "").replace("證", "증권")
    for pat, std in CANON:
        if re.search(pat, n):
            return std
    n = re.sub(r"(증권)+$", "증권", n)
    return n


def build_output(spot: float, today) -> dict:
    cache = load_cache()
    items = {i["id"]: i for i in news.load()}
    rows = []
    for id_, c in cache.items():
        it = items.get(id_)
        if not it or not c["is_forecast"] or not c["institution"] or re.fullmatch(r"(증권가|증권사|증권업계|외국계|해외\s*IB|IB|투자은행|전문가들?|시장|애널리스트)", re.sub(r"\s+", "", c["institution"])):
            continue  # 특정 기관이 아닌 일반 표현은 제외
        lo, hi = c["level_low"], c["level_high"]
        if lo and not (900 <= lo <= 2200 and (not hi or 900 <= hi <= 2200)):
            lo = hi = 0  # 환율 수준으로 보기 어려운 값은 버린다
        rows.append({"institution": canon_institution(c["institution"]), "published": it["published"][:10], "horizon": c["horizon"], "low": lo or None, "high": hi or None,
                     "view": c["view"], "summary": c["summary"], "title": it["title"], "link": it["link"], "press": it["press"], "verify": True,
                     "source": "언론 보도 인용(원문 미확인)", "by": "AI 추출"})
    if MANUAL.exists():
        m = yaml.safe_load(MANUAL.read_text(encoding="utf-8")) or {}
        for r in m.get("reports", []) or []:
            rows.append({"institution": canon_institution(r["institution"]), "published": str(r["published"]), "horizon": r.get("horizon", ""), "low": r.get("low"), "high": r.get("high", r.get("low")),
                         "view": r.get("view", "none"), "summary": r.get("rationale", ""), "title": r.get("title", ""), "link": r.get("link", ""), "press": r.get("source", ""),
                         "verify": bool(r.get("verify", True)), "source": r.get("source", "수기 입력"), "by": "수기"})
    # 같은 기관·날짜·수준에서 시점 표기만 비어 있는 중복은 시점이 있는 쪽만 남긴다
    best = {}
    for r in rows:
        k2 = (r["institution"], r["published"], r["low"], r["high"])
        if k2 not in best or (not best[k2]["horizon"] and r["horizon"]):
            best[k2] = r
    rows = list(best.values())
    seen, dedup = set(), []
    for r in sorted(rows, key=lambda r: (r["published"], r["by"] == "수기"), reverse=True):  # 같은 기관·날짜·시점·수준 중복 보도는 하나만(수기 우선)
        k = (r["institution"], r["published"], r["horizon"], r["low"], r["high"])
        if k in seen:
            continue
        seen.add(k); dedup.append(r)
    rows = dedup
    # 컨센서스: 최근 5영업일, 기관별 최신 1건, 수준이 있는 전망만
    since = news_window_start(today)
    latest = {}
    for r in sorted(rows, key=lambda r: r["published"]):
        if r["published"] >= since and r["low"]:
            latest[r["institution"]] = r
    mids = sorted((r["low"] + (r["high"] or r["low"])) / 2 for r in latest.values())
    cons = {"n": len(mids), "median": mids[len(mids) // 2] if mids else None, "min": mids[0] if mids else None, "max": mids[-1] if mids else None,
            "spot": spot, "since": since, "views": {v: sum(1 for r in latest.values() if r["view"] == v) for v in ("krw_weak", "krw_strong", "range", "none")}}
    return {"reports": rows[:200], "consensus": cons, "note": "원문 보고서가 아니라 언론 보도 제목에서 AI로 추출한 목록입니다. 기관명·수준·시점은 제목에 나온 것만 담았고 원문과 다를 수 있습니다."}


def news_window_start(today, n=5) -> str:
    d, k = today, 0
    while True:
        if d.weekday() < 5:
            k += 1
            if k == n:
                return d.isoformat()
        d -= timedelta(days=1)
