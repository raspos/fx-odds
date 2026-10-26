"""뉴스 압력 AI 보조 판단(OpenAI, 구조화 출력). 규칙이 놓친 환율 관련 제목만 배치로 판단하고 기사 ID 로 캐시한다.

원칙: 제목만 본다(본문·요약 없음). 제목에 없는 사실을 추정하지 않고, 확신이 없으면 '유보'. 같은 기사는 다시 호출하지 않는다.
키(OPENAI_API_KEY)가 없으면 건너뛰며 규칙 판단만으로 동작한다. 모델은 날짜 고정판을 쓰고 응답에 모델명을 남긴다.
"""
from __future__ import annotations
import csv, json, os
from datetime import datetime, timedelta
import requests
from common import DATA, now_kst, redact
import news

CACHE = DATA / "ai_news.jsonl"
USAGE = DATA / "ai_usage.csv"
MODEL = os.environ.get("FXODDS_AI_MODEL", "gpt-5.4-mini-2026-03-17")
EFFORT = "medium"
BATCH = 20
MAX_NEW_PER_RUN = 160   # 실행당 판단 상한(비용 상한)
AGREE_SAMPLE = 20       # 규칙 판단 기사 중 일치율 점검용 표본
WINDOW_DAYS = 3
TOPICS = ["dollar", "flow", "krrate", "jpy", "cny", "oil", "risk", "ext", "krw", "other"]

SYSTEM = """당신은 원/달러 환율 뉴스 분류기다. 입력은 기사 제목뿐이다. 각 제목이 '달러당 원화값(원/달러 환율)'에 어떤 방향의 압력으로 작용하는지 판단한다.
규칙:
- direction: krw_weak(환율 상승·원화 약세 압력), krw_strong(환율 하락·원화 강세 압력), hold(방향 불명·상반·환율과 무관).
- 제목에 없는 사실을 추정하지 마라. 확신이 없으면 hold.
- 이미 일어난 환율 변동을 전하는 결과 보도('환율 하락')는 topic=krw 로 두고 direction 은 보도된 방향으로 적되 strength 는 1.
- 원인(외국인 매매, 미국 금리, 달러, 엔·위안, 유가, 위험회피, 한국 금리, 무역·경상수지)이 제목에 분명할 때만 해당 topic 으로 분류한다.
- relevant=false 는 환율과 무관한 기사(주식 종목, 부동산, 코인, 연예 등).
- strength: 1(약함) 2(보통) 3(강함). reason 은 한 문장(40자 이내)으로 제목 근거만 적는다."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["id", "relevant", "topic", "direction", "strength", "reason"],
    "properties": {"id": {"type": "string"}, "relevant": {"type": "boolean"}, "topic": {"type": "string", "enum": TOPICS},
                   "direction": {"type": "string", "enum": ["krw_weak", "krw_strong", "hold"]}, "strength": {"type": "integer", "enum": [1, 2, 3]},
                   "reason": {"type": "string"}}}}}}


def load_cache() -> dict:
    if not CACHE.exists():
        return {}
    out = {}
    for l in CACHE.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l); out[r["id"]] = r
    return out


def append_cache(rows: list[dict]) -> None:
    with CACHE.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def log_usage(calls: int, inp: int, out: int, reasoning: int) -> None:
    new = not USAGE.exists()
    with USAGE.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "model", "calls", "input", "output", "reasoning"])
        w.writerow([now_kst().isoformat(timespec="minutes"), MODEL, calls, inp, out, reasoning])


def call(batch: list[dict]) -> tuple[list[dict], dict]:
    user = "다음 제목들을 판단하라. 각 항목의 id 를 그대로 돌려줘라.\n" + "\n".join(f"{b['id']}\t{b['title']}" for b in batch)
    body = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], "max_completion_tokens": 6000,
            "reasoning_effort": EFFORT, "response_format": {"type": "json_schema", "json_schema": {"name": "fx_news", "strict": True, "schema": SCHEMA}}}
    r = requests.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}, json=body, timeout=180)
    r.raise_for_status()
    j = r.json()
    ch = j["choices"][0]
    if ch.get("finish_reason") == "length":
        raise RuntimeError("출력 한도 초과")
    return json.loads(ch["message"]["content"])["items"], j.get("usage", {})


def run() -> dict:
    if not os.environ.get("OPENAI_API_KEY"):
        return {"ok": False, "why": "OPENAI_API_KEY 없음(규칙 판단만 사용)"}
    cache = load_cache()
    cutoff = (now_kst() - timedelta(days=WINDOW_DAYS)).isoformat()
    cand, sample = [], []
    for it in news.load():
        if it.get("official") or it["published"] < cutoff or it["id"] in cache:
            continue
        j = news.judge(it)
        if j["status"] == "분류 불가" and news.RELEVANT.search(it["title"]) and not news.EXCLUDE.search(it["title"]):
            cand.append(it)
        elif j["status"] == "판단" and len(sample) < AGREE_SAMPLE:
            sample.append(it)
    todo = (cand[:MAX_NEW_PER_RUN] + sample)
    if not todo:
        return {"ok": True, "added": 0}
    rows, calls, tin, tout, tr = [], 0, 0, 0, 0
    try:
        for i in range(0, len(todo), BATCH):
            b = todo[i:i + BATCH]
            res, u = call(b)
            calls += 1; tin += u.get("prompt_tokens", 0); tout += u.get("completion_tokens", 0)
            tr += (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
            ids = {x["id"] for x in b}
            for x in res:
                if x["id"] in ids:
                    rows.append({**x, "model": MODEL, "at": now_kst().isoformat(timespec="minutes"), "sampled": any(s["id"] == x["id"] for s in sample)})
    except Exception as e:
        err = redact(type(e).__name__ + " " + str(e))[:160]
        if rows:
            append_cache(rows); log_usage(calls, tin, tout, tr)
        return {"ok": False, "why": err, "added": len(rows)}
    append_cache(rows); log_usage(calls, tin, tout, tr)
    return {"ok": True, "added": len(rows), "calls": calls, "tokens_in": tin, "tokens_out": tout}


def to_judgement(r: dict) -> dict:
    """캐시 행 -> news.judge 와 같은 형식."""
    if not r["relevant"] or r["direction"] == "hold":
        return {"topic": None if not r["relevant"] else (r["topic"] if r["topic"] != "other" else None), "dir": 0, "strength": 0,
                "why": "AI: " + r["reason"], "status": "AI 판단 유보" if r["relevant"] else "분류 불가"}
    t = r["topic"] if r["topic"] != "other" else "krw"
    return {"topic": t, "dir": 1 if r["direction"] == "krw_weak" else -1, "strength": int(r["strength"]), "why": "AI: " + r["reason"], "status": "AI 판단"}
