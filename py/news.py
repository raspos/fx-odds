"""FX INTELLIGENCE v0.1: 네이버 뉴스 검색 API(NAVER API HUB) 수집 -> 사건 묶기 -> 인과 규칙 기반 방향 판단 -> 뉴스 압력 지수(NPI).

저장은 제목·링크·발행 시각까지만(요약·본문 미저장, 저작권). 방향은 '감성'이 아니라 환율에 작용하는 경제적 인과 규칙으로 정한다.
규칙이 맞지 않거나 상반된 규칙이 함께 맞으면 '판단 유보'로 두고 점수에 넣지 않는다.
같은 날 같은 주제(달러 가족은 하나로)의 기사는 하나의 사건 그룹이며 기사 수는 강도에 영향을 주지 않는다.
NPI 는 확률이 아니며 검증 전의 실험 지수다. 매일 값을 append-only 로 기록해 이후 환율과의 관계를 실시간으로 검증한다.
"""
from __future__ import annotations
import hashlib, html, json, os, re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import numpy as np
import requests
from common import DATA, KST, now_kst, redact

NEWS = DATA / "news.jsonl"
NPI_LOG = DATA / "npi_log.csv"
ENDPOINT = os.environ.get("NAVER_ENDPOINT", "https://naverapihub.apigw.ntruss.com/search/v1/news")
QUERIES = ["원달러 환율", "원화 약세", "원화 강세", "달러 강세", "연준 금리", "미국 국채금리", "외국인 순매도 코스피", "외국인 순매수 코스피",
           "엔화 약세", "위안화 환율", "국제유가", "한국은행 기준금리", "무역수지 수출", "경상수지", "중동 지정학 환율", "대만 달러 반도체",
           "증권사 환율 전망", "달러-원 전망 연말", "내년 환율 전망 증권", "환율 전망 상향 하향", "원/달러 전망 리서치", "외환 전망 골드만삭스", "원화 전망 투자은행",
           "해외 IB 환율 전망", "골드만삭스 원달러 전망", "JP모건 원화 전망", "모건스탠리 환율 전망", "씨티 원달러 전망", "UBS 원화 전망", "노무라 원달러 전망", "HSBC 원화 전망", "바클레이스 환율 전망", "BofA 원달러 전망", "도이치뱅크 원화 전망", "맥쿼리 원화 전망"]
KEEP_DAYS = 45
HALF_LIFE = 7.0  # 일. 사건 영향의 반감기(가정, 검증 전)

# (정규식, 주제, 방향: +1 원화 약세(환율 상승) / -1 원화 강세(환율 하락), 근거 설명)
RULES = [
    (r"달러\s*(강세|급등|상승)|달러인덱스\s*(상승|급등)|킹달러", "dollar", +1, "달러 강세는 원화 약세 압력"),
    (r"달러\s*(약세|하락|급락)|달러인덱스\s*(하락|급락)", "dollar", -1, "달러 약세는 원화 강세 압력"),
    (r"(미|美|미국)?\s*국채\s*금리\s*(상승|급등|오름|뛰)|연준.{0,12}(금리\s*인상|매파|긴축|인하\s*지연|인하\s*기대\s*(후퇴|약화))|고금리\s*장기화", "dollar", +1, "미국 금리 상승·긴축 기조는 달러 강세·원화 약세 압력"),
    (r"(미|美|미국)?\s*국채\s*금리\s*(하락|급락|내림)|연준.{0,12}(금리\s*인하|비둘기|완화)|인하\s*기대\s*(확대|커)", "dollar", -1, "미국 금리 하락·완화 기대는 달러 약세·원화 강세 압력"),
    (r"외국인.{0,10}(순매도|매도\s*우위|자금\s*이탈|이탈)|외국인\s*(팔자|매도세)", "flow", +1, "외국인 자금 유출은 원화 약세 압력"),
    (r"외국인.{0,10}(순매수|매수\s*우위|자금\s*유입|유입)|외국인\s*(사자|매수세)", "flow", -1, "외국인 자금 유입은 원화 강세 압력"),
    (r"(한은|한국은행|금통위).{0,12}(금리\s*인하|인하\s*가능성|비둘기)", "krrate", +1, "한국 금리 인하는 내외금리차 확대로 원화 약세 압력"),
    (r"(한은|한국은행|금통위).{0,12}(금리\s*인상|매파|인상\s*가능성)", "krrate", -1, "한국 금리 인상은 내외금리차 축소로 원화 강세 압력"),
    (r"엔화\s*(약세|급락)|엔저|엔/?달러\s*(상승|급등)", "jpy", +1, "엔화 약세는 원화 동반 약세 압력(동조화 경향)"),
    (r"엔화\s*(강세|급등)|엔고|엔/?달러\s*(하락|급락)", "jpy", -1, "엔화 강세는 원화 동반 강세 압력(동조화 경향)"),
    (r"위안화\s*(약세|절하|급락)|위안\s*절하", "cny", +1, "위안화 약세는 원화 동반 약세 압력"),
    (r"위안화\s*(강세|절상)|위안\s*절상", "cny", -1, "위안화 강세는 원화 동반 강세 압력"),
    (r"(국제)?유가\s*(상승|급등|강세)|WTI\s*(상승|급등)|두바이유\s*(상승|급등)", "oil", +1, "유가 상승은 원유 수입국 한국의 원화 약세 압력"),
    (r"(국제)?유가\s*(하락|급락|약세)|WTI\s*(하락|급락)|두바이유\s*(하락|급락)", "oil", -1, "유가 하락은 원화 강세 압력"),
    (r"(?<!완화\s)(위험\s*회피|리스크\s*오프|지정학\s*(리스크|위험|불안)|무력\s*충돌|전쟁\s*(확산|격화)|중동\s*(긴장|불안))(?!\s*(완화|해소|진정|누그|둔화|약화))(?!.{0,6}완화\s*기대)", "risk", +1, "위험회피는 원화 약세 압력"),
    (r"(긴장|불안|지정학\s*(리스크|위험))\s*(완화|해소|진정|누그)|휴전|협상\s*타결|정전", "risk", -1, "지정학 긴장 완화는 위험선호를 통해 원화 강세 압력"),
    (r"위험\s*선호|리스크\s*온", "risk", -1, "위험선호는 원화 강세 압력"),
    (r"(무역|경상)\s*수지\s*적자", "ext", +1, "대외거래 악화는 원화 약세 압력"),
    (r"(무역|경상)\s*수지\s*(흑자|개선)", "ext", -1, "대외거래 개선은 원화 강세 압력"),
    (r"환율\s*(상승|급등|치솟|오름)|원화\s*(약세|급락)|원\s*[/·]?\s*달러\s*(상승|급등)|1[,]?[3-5]\d\d원\s*(돌파|넘)", "krw", +1, "환율 상승 보도(결과 보도, 원인 아님)"),
    (r"환율.{0,20}(연저점|2년\s*만에\s*최저|최저\s*수준|최저치)|원화\s*(가치\s*)?(상승|랠리)|환율\s*뚝", "krw", -1, "환율 하락 보도(결과 보도, 원인 아님)"),
    (r"환율.{0,20}(연고점|최고치|급등세)", "krw", +1, "환율 상승 보도(결과 보도, 원인 아님)"),
    (r"네고\s*(물량)?.{0,6}(유입|출회|쏟|영향|로)?", "ext", -1, "수출업체 달러 매도(네고)는 원화 강세 압력"),
    (r"강달러", "dollar", +1, "달러 강세는 원화 약세 압력"),
    (r"위안화\s*기준치.{0,20}절상|위안화\s*고시.{0,20}절상", "cny", -1, "위안화 고시환율 절상은 위안화 강세 신호"),
    (r"위안화\s*기준치.{0,20}절하|위안화\s*고시.{0,20}절하", "cny", +1, "위안화 고시환율 절하는 위안화 약세 신호"),
    (r"달러[-/]?엔\s*(상승|급등|오름)", "jpy", +1, "엔화 약세는 원화 동반 약세 압력(동조화 경향)"),
    (r"달러[-/]?엔\s*(하락|급락|내림)", "jpy", -1, "엔화 강세는 원화 동반 강세 압력(동조화 경향)"),
    (r"외국인.{0,12}(팔았|팔고|팔자|팔아|매도)", "flow", +1, "외국인 자금 유출은 원화 약세 압력"),
    (r"환율\s*(하락|급락|내림|떨어)|원화\s*(강세|급등)|원\s*[/·]?\s*달러\s*(하락|급락)", "krw", -1, "환율 하락 보도(결과 보도, 원인 아님)"),
]
FAMILY = {"report": "report", "dollar": "dollar", "jpy": "dollar", "cny": "dollar", "flow": "flow", "krrate": "krrate", "oil": "oil", "risk": "risk", "ext": "ext", "krw": "krw"}
TOPIC_KO = {"other": "기타", "report": "공식 보고서·발표", "dollar": "달러·미국 금리", "flow": "외국인 자금", "krrate": "한국 금리", "jpy": "엔화", "cny": "위안화", "oil": "유가", "risk": "위험회피·지정학", "ext": "대외거래", "krw": "원화 환율 보도"}
STRONG = re.compile(r"급(등|락|증|감|반등)|폭(등|락)|사상|최고|최저|쇼크|우려|전격")
NEG = re.compile(r"(아니|않|없|전망\s*과\s*달리|부인|일축)")


def clean(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", s or "")).split())


def press_from(url: str) -> str:
    m = re.match(r"https?://(?:www\.|m\.)?([^/]+)", url or "")
    return m.group(1) if m else ""


def norm_title(t: str) -> str:
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|[\"'“”‘’…·,.!?]", "", t)
    return re.sub(r"\s+", "", t)[:40]


def load() -> list[dict]:
    if not NEWS.exists():
        return []
    return [json.loads(l) for l in NEWS.read_text(encoding="utf-8").splitlines() if l.strip()]


def save(items: list[dict]) -> None:
    NEWS.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items), encoding="utf-8")


def parse_items(payload: dict, query: str) -> list[dict]:
    out = []
    for it in payload.get("items", []):
        link = it.get("originallink") or it.get("link")
        if not link:
            continue
        try:
            ts = parsedate_to_datetime(it["pubDate"]).astimezone(KST)
        except (KeyError, TypeError, ValueError):
            ts = now_kst()
        out.append({"id": hashlib.sha1(link.encode()).hexdigest()[:12], "title": clean(it.get("title")), "summary": "",  # 요약·본문은 저장하지 않는다(제목·링크·시각만)
                    
                    "link": link, "press": press_from(link), "published": ts.isoformat(timespec="minutes"), "queries": [query],
                    "first_seen": now_kst().isoformat(timespec="minutes")})
    return out


def merge(existing: list[dict], new: list[dict], now: datetime) -> list[dict]:
    by_link = {x["link"]: x for x in existing}
    titles = {norm_title(x["title"]): x for x in existing}
    for x in new:
        if x["link"] in by_link:  # 최초 수집 시각 보존
            by_link[x["link"]]["queries"] = sorted(set(by_link[x["link"]]["queries"]) | set(x["queries"])); continue
        d = titles.get(norm_title(x["title"]))
        if d:  # 같은 제목 재전송은 하나로 합치고 매체만 기록
            d["dup_press"] = sorted(set(d.get("dup_press", [])) | {x["press"]}); continue
        by_link[x["link"]] = x; titles[norm_title(x["title"])] = x
    cutoff = now - timedelta(days=KEEP_DAYS)
    return sorted([x for x in by_link.values() if datetime.fromisoformat(x["published"]) >= cutoff], key=lambda x: x["published"], reverse=True)


OFFICIAL = [  # (표시명, URL, 매체코드)
    ("한국은행 보도자료", "https://www.bok.or.kr/portal/bbs/P0000559/news.rss?menuNo=200690", "bok.or.kr"),
    ("미국 연준 보도자료", "https://www.federalreserve.gov/feeds/press_all.xml", "federalreserve.gov"),
    ("BIS 발간물", "https://www.bis.org/doclist/bis_fsi_publs.rss", "bis.org"),
]


def collect_official(limit=40) -> dict:
    import xml.etree.ElementTree as ET
    got, errs = [], []
    for name, url, host in OFFICIAL:
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30); r.raise_for_status()
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                link = (it.findtext("link") or "").strip(); title = clean(it.findtext("title"))
                if not link or not title:
                    continue
                try:
                    ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST)
                except Exception:
                    try:
                        ts = datetime.fromisoformat((it.findtext("{http://purl.org/dc/elements/1.1/}date") or "")[:19]).replace(tzinfo=KST)
                    except Exception:
                        ts = now_kst()
                got.append({"id": hashlib.sha1(link.encode()).hexdigest()[:12], "title": title, "summary": "", "link": link, "press": name, "official": True,
                            "published": ts.isoformat(timespec="minutes"), "queries": ["official"], "first_seen": now_kst().isoformat(timespec="minutes")})
        except Exception as e:
            errs.append(f"{name}: {redact(type(e).__name__)}")
    got = sorted(got, key=lambda x: x["published"], reverse=True)
    per = {}
    keep = []
    for x in got:  # 기관별 최근 limit 건
        per[x["press"]] = per.get(x["press"], 0) + 1
        if per[x["press"]] <= limit:
            keep.append(x)
    if keep:
        save(merge(load(), keep, now_kst()))
    return {"ok": not errs and bool(keep), "received": len(keep), "errors": errs}


def collect(display=100) -> dict:
    cid, sec = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and sec):
        return {"ok": False, "why": "NAVER_CLIENT_ID/SECRET 없음"}
    got, errs = [], []
    for q in QUERIES:
        try:
            r = requests.get(ENDPOINT, params={"query": q, "display": display, "sort": "date"},
                             headers={"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": sec}, timeout=20)
            r.raise_for_status()
            got += parse_items(r.json(), q)
        except Exception as e:
            errs.append(f"'{q}': {redact(type(e).__name__ + ' ' + str(e))[:80]}")
    if not got:
        return {"ok": False, "why": "; ".join(errs)[:300] or "0건"}
    items = merge(load(), got, now_kst()); save(items)
    return {"ok": not errs, "received": len(got), "kept": len(items), "errors": errs}


# ------------------------------ 분석 ------------------------------
RELEVANT = re.compile(r"환율|원화|원\s*[/·]\s*달러|달러|외환|연준|Fed|FOMC|국채|금리|외국인|엔화|엔저|엔고|위안|유가|WTI|두바이유|무역수지|경상수지|지정학|위험\s*회피|리스크")
EXCLUDE = re.compile(r"코인|비트코인|이더리움|가상자산|암호화폐|부동산|분양|아파트|청약|주택|대출\s*금리|예금|적금|보험|연예|스포츠")


EN_RULES = [
    (r"raises?.{0,40}(target range|federal funds rate|discount rate)|rate (hike|increase)", "dollar", +1, "미국 정책금리 인상은 원화 약세 압력"),
    (r"lowers?.{0,40}(target range|federal funds rate|discount rate)|rate (cut|reduction)", "dollar", -1, "미국 정책금리 인하는 원화 강세 압력"),
]


def judge(it: dict) -> dict:
    if it.get("official"):
        hits = [(t, d, w) for pat, t, d, w in RULES if re.search(pat, it["title"])] + [(t, d, w) for pat, t, d, w in EN_RULES if re.search(pat, it["title"], re.I)]
        dirs = {d for _, d, _ in hits}
        if len(dirs) == 1:
            t, d, w = hits[0]
            return {"topic": t, "dir": int(d), "strength": 2, "why": w + " (공식 발표 제목 기준)", "status": "판단"}
        return {"topic": "report", "dir": 0, "strength": 0, "why": "공식 발표 — 제목만으로 방향을 판단하지 않음(원문 확인 필요)", "status": "공식 발표"}
    if not RELEVANT.search(it["title"]) or EXCLUDE.search(it["title"]):
        return {"topic": None, "dir": 0, "strength": 0, "why": "", "status": "분류 불가"}
    hits = []
    for pat, topic, d, why in RULES:
        if re.search(pat, it["title"]):  # 제목만 본다(요약은 잡음이 많다)
            hits.append((topic, d, why))
    if not hits:
        return {"topic": None, "dir": 0, "strength": 0, "why": "", "status": "분류 불가"}
    topics = {FAMILY[t] for t, _, _ in hits}
    # 제목에서 주제별 상반된 방향이 함께 잡히면 유보
    main = max(hits, key=lambda h: (h[0] != "krw",))
    dirs = {d for t, d, _ in hits if t != "krw"} or {d for _, d, _ in hits}
    if len(dirs) > 1 or NEG.search(it["title"]):
        return {"topic": main[0], "dir": 0, "strength": 0, "why": "상반된 신호 또는 부정 표현이 있어 판단 유보", "status": "판단 유보"}
    s = 1 + (1 if STRONG.search(it["title"]) else 0) + (1 if len({t for t, _, _ in hits}) >= 2 else 0)
    return {"topic": main[0], "dir": int(main[1]), "strength": min(3, s), "why": main[2], "status": "판단"}


def _score(rows: list[dict], today) -> dict:
    """판단된 기사 -> 사건 그룹 -> 뉴스 압력 지수. 같은 날·주제 가족·방향의 기사는 하나(강도 max)."""
    groups = {}
    for r in rows:
        if r["dir"] == 0 or r["topic"] in (None, "report"):
            continue
        key = (r["date"], FAMILY.get(r["topic"], r["topic"]), r["dir"])
        g = groups.setdefault(key, {"date": r["date"], "family": FAMILY.get(r["topic"], r["topic"]), "dir": r["dir"], "strength": 0, "articles": [], "why": r["why"], "topics": set()})
        g["strength"] = max(g["strength"], r["strength"]); g["articles"].append(r["id"]); g["topics"].add(r["topic"])
    byfd = {}
    for (d, f, dr), g in groups.items():
        byfd.setdefault((d, f), []).append(g)
    final = []
    for gs in byfd.values():  # 같은 날 같은 가족에서 방향이 갈리면 상쇄하지 않고 둘 다 제외
        if len(gs) > 1:
            for g in gs:
                g["conflict"] = True
        final += gs
    S = 0.0
    for g in final:
        if g.get("conflict") or g["family"] == "krw":  # 결과 보도는 원인이 아니므로 점수 제외
            continue
        age = (today - datetime.fromisoformat(g["date"]).date()).days
        if age >= 0:
            S += g["dir"] * g["strength"] * 0.5 ** (age / HALF_LIFE)
    npi = float(100 * np.tanh(S / 15.0))
    win = {}
    for label, days in (("24h", 1), ("7d", 7), ("30d", 30)):
        sel = [g for g in final if 0 <= (today - datetime.fromisoformat(g["date"]).date()).days < days + (0 if days > 1 else 1) and g["family"] != "krw" and not g.get("conflict")]
        win[label] = {"up": sum(1 for g in sel if g["dir"] > 0), "down": sum(1 for g in sel if g["dir"] < 0), "articles": sum(len(g["articles"]) for g in sel)}
    return {"groups": [{**g, "topics": sorted(g["topics"])} for g in final], "npi": round(npi, 1), "S": round(S, 2), "windows": win}


def analyze(items: list[dict], today, ai: dict | None = None) -> dict:
    """ai: ai_news 캐시({기사id: 행}). 규칙이 판단하지 못한 기사에만 AI 판단을 얹고, 규칙 판단 기사 중 AI 표본은 일치율 점검에만 쓴다."""
    import ai_news
    rows_rule, rows_all, agree = [], [], []
    for it in items:
        j = judge(it); pub = datetime.fromisoformat(it["published"])
        base = {**{k: it[k] for k in ("id", "title", "summary", "link", "press", "published", "first_seen")}, "dup_press": it.get("dup_press", []),
                "official": bool(it.get("official")), "date": pub.date().isoformat()}
        rr = {**base, **j, "by": "rule"}
        rows_rule.append(rr)
        a = (ai or {}).get(it["id"])
        if a and not it.get("official"):
            aj = ai_news.to_judgement(a)
            if j["status"] in ("분류 불가", "판단 유보"):
                rows_all.append({**base, **aj, "by": "ai", "ai_model": a["model"]})
                continue
            if a.get("sampled") and j["dir"] != 0:
                agree.append((j["dir"], aj["dir"]))
        rows_all.append(rr)
    sc_rule, sc_all = _score(rows_rule, today), _score(rows_all, today)
    n_ag = sum(1 for r, a in agree if a != 0)
    return {"rows": rows_all, "groups": sc_all["groups"], "npi": sc_all["npi"], "S": sc_all["S"], "windows": sc_all["windows"], "npi_rule": sc_rule["npi"], "windows_rule": sc_rule["windows"],
            "n_articles": len(rows_all), "n_judged": sum(1 for r in rows_all if r["dir"] != 0), "n_hold": sum(1 for r in rows_all if "유보" in r["status"]),
            "n_unclassified": sum(1 for r in rows_all if r["status"] == "분류 불가"), "n_official": sum(1 for r in rows_all if r["official"]),
            "n_ai": sum(1 for r in rows_all if r.get("by") == "ai" and r["dir"] != 0),
            "agreement": {"n": len(agree), "n_dir": n_ag, "same": sum(1 for r, a in agree if a == r), "opposite": sum(1 for r, a in agree if a not in (0, r)), "ai_hold": sum(1 for r, a in agree if a == 0)}}


def build_output(today, status: dict) -> dict:
    items = load()
    if not items:
        return {"available": False, "status": status, "note": "뉴스 수집 전입니다(NAVER_CLIENT_ID/SECRET 필요).", "queries": QUERIES}
    cutoff = (today - timedelta(days=30)).isoformat()
    import ai_news
    a = analyze([i for i in items if i["published"][:10] >= cutoff], today, ai_news.load_cache())
    arts = [r for r in a["rows"]]
    return {"available": True, "status": status, "npi": a["npi"], "npi_rule": a["npi_rule"], "windows_rule": a["windows_rule"], "agreement": a["agreement"], "S": a["S"], "windows": a["windows"], "half_life_days": HALF_LIFE,
            "counts": {k: a[k] for k in ("n_articles", "n_judged", "n_hold", "n_unclassified", "n_official", "n_ai")}, "groups": sorted(a["groups"], key=lambda g: g["date"], reverse=True),
            "articles": arts[:400], "topics": TOPIC_KO, "queries": QUERIES, "last_collected": max(i["first_seen"] for i in items),
            "rules": [{"topic": t, "dir": d, "why": w} for _, t, d, w in RULES]}


def log_npi(today, npi: float) -> None:
    """뉴스 압력 지수를 날짜별로 한 번만 추가 기록한다(덮어쓰기 금지)."""
    import csv
    seen = set()
    if NPI_LOG.exists():
        seen = {r[0] for r in csv.reader(NPI_LOG.open(encoding="utf-8"))}
    if today.isoformat() in seen:
        return
    new = not NPI_LOG.exists()
    with NPI_LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "npi", "recorded_at"])
        w.writerow([today.isoformat(), npi, now_kst().isoformat(timespec="seconds")])
