"""뉴스 압력 AI 요약 코멘트(2문장). 이미 판단된 사건 그룹(제목·주제·방향·강도)만 입력으로 쓰고, 전망·권유·추정은 하지 않게 한다.
전체 수집 실행에서만 생성하고(방문자별 호출 없음), 입력 해시로 캐시한다. 키가 없거나 실패하면 마지막 코멘트를 그대로 둔다."""
from __future__ import annotations
import hashlib, json, os
import requests
from common import post_json_retry, DATA, now_kst, redact

CACHE = DATA / "ai_comment.jsonl"
MODEL = os.environ.get("FXODDS_AI_MODEL", "gpt-5.4-mini-2026-03-17")
FAMILY_KO = {"dollar": "달러·미국 금리·엔·위안", "flow": "외국인 자금", "krrate": "한국 금리", "oil": "유가", "risk": "위험회피·지정학", "ext": "대외거래", "krw": "원화 환율 보도"}

SYSTEM = """당신은 원/달러 환율 뉴스 압력 요약가다. 입력은 이미 분류된 사건 목록(날짜, 주제, 방향, 강도, 대표 제목)이다.
규칙:
- 정확히 두 문장, 합쳐서 150자 이내의 한국어.
- 입력에 있는 사건만 근거로 쓴다. 입력에 없는 사실·수치·이유를 만들지 마라.
- 가격 전망, 투자 권유, '오를 것/내릴 것' 같은 예측 표현 금지. '~압력으로 작용했다', '~보도가 이어졌다'처럼 서술한다.
- 방향: krw_weak=환율 상승·원화 약세 압력, krw_strong=환율 하락·원화 강세 압력. 양쪽이 섞여 있으면 둘 다 언급한다.
- 첫 문장은 우세한 쪽, 둘째 문장은 반대 방향 또는 눈에 띄는 변수."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["comment"], "properties": {"comment": {"type": "string"}}}


def pick(nj: dict, n=8) -> list[dict]:
    arts = {a["id"]: a for a in nj.get("articles", [])}
    rows = []
    for g in sorted(nj.get("groups", []), key=lambda g: (g["date"], g["strength"]), reverse=True):
        if g.get("conflict") or g["family"] == "krw":
            continue
        a = arts.get(g["articles"][0])
        if not a:
            continue
        rows.append({"date": g["date"], "topic": FAMILY_KO.get(g["family"], g["family"]), "direction": "krw_weak" if g["dir"] > 0 else "krw_strong",
                     "strength": g["strength"], "title": a["title"], "link": a["link"]})
        if len(rows) >= n:
            break
    return rows


def load() -> list[dict]:
    if not CACHE.exists():
        return []
    return [json.loads(l) for l in CACHE.read_text(encoding="utf-8").splitlines() if l.strip()]


def get(nj: dict, allow_generate: bool) -> dict | None:
    rows = pick(nj)
    if not rows:
        return None
    key = hashlib.sha1(json.dumps([[r["date"], r["topic"], r["direction"], r["strength"], r["title"]] for r in rows], ensure_ascii=False).encode()).hexdigest()[:16]
    cache = load()
    hit = next((c for c in cache if c["key"] == key), None)
    if hit:
        return {**hit, "basis": rows, "fresh": True}
    if allow_generate and os.environ.get("OPENAI_API_KEY"):
        try:
            user = "사건 목록:\n" + "\n".join(f"- {r['date']} | {r['topic']} | {r['direction']} | 강도{r['strength']} | {r['title']}" for r in rows)
            body = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], "max_completion_tokens": 1500,
                    "reasoning_effort": "low", "response_format": {"type": "json_schema", "json_schema": {"name": "fx_comment", "strict": True, "schema": SCHEMA}}}
            r = post_json_retry("https://api.openai.com/v1/chat/completions", headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}, body=body)
            ch = r.json()["choices"][0]
            if ch.get("finish_reason") == "length":
                raise RuntimeError("출력 한도 초과")
            text = json.loads(ch["message"]["content"])["comment"].strip()
            rec = {"key": key, "text": text[:220], "model": MODEL, "at": now_kst().isoformat(timespec="minutes")}
            with CACHE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return {**rec, "basis": rows, "fresh": True}
        except Exception as e:
            print("AI 코멘트 생성 실패:", redact(type(e).__name__ + " " + str(e))[:120])
    if cache:  # 생성하지 않는 빌드/실패: 마지막 코멘트를 시각과 함께 그대로 보여 준다(입력이 달라졌음을 표시)
        return {**cache[-1], "basis": rows, "fresh": False}
    return None
