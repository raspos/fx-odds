import { useMemo, useState } from "react";
import { J, sgn } from "../lib";

const bd = (d: string, ref: string) => {  // 평일 수 차이
  let n = 0; const a = new Date(d + "T00:00:00Z"), b = new Date(ref + "T00:00:00Z");
  for (const c = new Date(a); c < b; c.setUTCDate(c.getUTCDate() + 1)) { const w = c.getUTCDay(); if (w !== 0 && w !== 6) n++; }
  return n;
};

export function News({ N, refDate, asOf }: { N: J; refDate: string; asOf: string | null }) {
  const [win, setWin] = useState<"1" | "7" | "30">("7");
  const [topic, setTopic] = useState("all");
  const [dir, setDir] = useState<"all" | "up" | "down">("all");
  const [showHold, setShowHold] = useState(false);
  const arts: J[] = useMemo(() => (N.available ? N.articles : []), [N]);
  const list = useMemo(() => arts.filter((a) => {
    const age = bd(a.date, refDate);
    if (age > (win === "1" ? 0 : win === "7" ? 6 : 22)) return false;
    if (a.status === "분류 불가") return false;
    if (!showHold && a.dir === 0) return false;
    if (topic !== "all" && a.topic !== topic) return false;
    if (dir === "up" && a.dir <= 0) return false;
    if (dir === "down" && a.dir >= 0) return false;
    return true;
  }), [arts, win, topic, dir, showHold, refDate]);
  if (asOf) return <div className="card p-4 text-sm" style={{ color: "var(--ink-2)" }}>선택한 과거 날짜({asOf})에 당시 보존된 뉴스·보고서가 없어 현재 뉴스를 과거 분석처럼 보여 주지 않습니다. 최신 날짜로 돌아가면 표시됩니다.</div>;
  if (!N.available) return <div className="card p-4 text-sm">{N.note}</div>;
  const npi = N.npi as number; const W = N.windows;
  const dirTxt = npi > 8 ? "원화 약세(환율 상승) 뉴스 압력 우세" : npi < -8 ? "원화 강세(환율 하락) 뉴스 압력 우세" : "뚜렷한 방향 없음";
  return (
    <div className="space-y-4">
      <div className="card p-4 sm:p-5">
        <span className="rounded-full px-2 py-0.5 text-xs font-bold" style={{ background: "var(--warn-bg)", color: "var(--warn-ink)" }}>실험적 뉴스 압력 지수 · 확률 아님 · 검증 전</span>
        <div className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-1">
          <div className="num text-5xl font-black" style={{ color: npi >= 0 ? "var(--up)" : "var(--down)" }}>{sgn(npi, 0)}</div>
          <div className="pb-1 text-sm" style={{ color: "var(--ink-2)" }}>{dirTxt}</div>
        </div>
        <div className="relative mt-3 h-3 rounded-full" style={{ background: "linear-gradient(90deg,var(--down),var(--surface-2) 50%,var(--up))" }}>
          <div className="absolute -top-1 h-5 w-1 rounded" style={{ left: `calc(${(npi + 100) / 2}% - 2px)`, background: "var(--ink)" }} /></div>
        <div className="mt-1 flex justify-between text-[11px]" style={{ color: "var(--ink-3)" }}><span>−100 원화 강세 압력</span><span>0</span><span>+100 원화 약세 압력</span></div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center text-[12px]">
          {([["24h", "24시간"], ["7d", "7일"], ["30d", "30일"]] as const).map(([k, l]) => (
            <div key={k} className="rounded-lg p-2" style={{ background: "var(--surface-2)" }}>
              <div style={{ color: "var(--ink-3)" }}>{l} 사건</div>
              <div className="num font-bold"><span style={{ color: "var(--up)" }}>약세 {W[k].up}</span> · <span style={{ color: "var(--down)" }}>강세 {W[k].down}</span></div>
            </div>))}
        </div>
        <p className="mt-3 text-[12px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
          네이버 뉴스 검색(제목·링크만)에서 수집한 기사를 인과 규칙(예: 외국인 매도 → 원화 약세, 미국 금리 하락 → 원화 강세)으로 분류했습니다. 같은 날 같은 주제의 기사는 하나의 사건으로 묶어 기사 수가 점수를 키우지 않고,
          사건 영향은 반감기 {N.half_life_days}일로 줄어듭니다. 상반된 신호나 부정 표현이 있으면 '판단 유보', 환율 결과 보도("환율 하락")는 원인이 아니라서 점수에서 뺍니다.
          <b> 과거 환율과의 관계는 아직 검증되지 않았고</b>(과거 뉴스 보존본 없음) 오늘부터 기록을 쌓아 공개 검증합니다. 확률 전망에는 반영하지 않습니다.
        </p>
        <p className="mt-1 text-[11px]" style={{ color: "var(--ink-3)" }}>수집 {N.counts.n_articles}건 · 판단 {N.counts.n_judged}건 · 유보 {N.counts.n_hold}건 · 분류 불가 {N.counts.n_unclassified}건 · 공식 발표 {N.counts.n_official}건 · 마지막 수집 {N.last_collected.replace("T", " ")}</p>
      </div>
      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">공식 보고서·발표 (한국은행 · 연준 · BIS)</h3>
        <p className="mt-1 text-[12px]" style={{ color: "var(--ink-3)" }}>기관이 직접 공개한 보도자료·의사록·발간물의 제목과 원문 링크입니다. 제목만으로 방향을 단정하지 않으며, 원문을 확인해야 합니다.</p>
        <div className="mt-2 divide-y" style={{ borderColor: "var(--line)" }}>
          {arts.filter((a) => a.official).slice(0, 12).map((a) => (
            <div key={a.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-1.5 text-[13px]">
              <span className="num w-24 shrink-0 text-[11px]" style={{ color: "var(--ink-3)" }}>{a.date}</span>
              <span className="w-32 shrink-0 text-[11px]" style={{ color: "var(--ink-2)" }}>{a.press}</span>
              <a href={a.link} target="_blank" rel="noreferrer" className="min-w-0 flex-1 underline-offset-2 hover:underline">{a.title}</a>
              {a.dir !== 0 && <b className="text-[11px]" style={{ color: a.dir > 0 ? "var(--up)" : "var(--down)" }}>{a.dir > 0 ? "원화 약세 압력" : "원화 강세 압력"}</b>}
            </div>))}
          {arts.filter((a) => a.official).length === 0 && <div className="py-2 text-[13px]" style={{ color: "var(--ink-3)" }}>수집된 공식 발표가 없습니다.</div>}
        </div>
      </div>
      <div className="card p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="mr-auto text-lg font-bold">뉴스 사건 타임라인</h3>
          {([["1", "24시간"], ["7", "7영업일"], ["30", "30일"]] as const).map(([k, l]) => <button key={k} className="btn" aria-pressed={win === k} onClick={() => setWin(k)}>{l}</button>)}
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button className="btn" aria-pressed={topic === "all"} onClick={() => setTopic("all")}>전체 주제</button>
          {Object.entries(N.topics).map(([k, v]) => <button key={k} className="btn" aria-pressed={topic === k} onClick={() => setTopic(k)}>{v as string}</button>)}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {([["all", "방향 전체"], ["up", "원화 약세 압력"], ["down", "원화 강세 압력"]] as const).map(([k, l]) => <button key={k} className="btn" aria-pressed={dir === k} onClick={() => setDir(k)}>{l}</button>)}
          <button className="btn" aria-pressed={showHold} onClick={() => setShowHold(!showHold)}>판단 유보 포함</button>
        </div>
        <p className="mt-2 text-[12px]" style={{ color: "var(--ink-3)" }}>{list.length}건 표시</p>
      </div>
      {list.slice(0, 60).map((a) => (
        <div key={a.id} className="card p-3.5">
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: "var(--ink-3)" }}>
            <span className="num">{a.published.replace("T", " ").slice(0, 16)}</span><span>· {a.press}</span>
            <span className="rounded-full px-2 py-0.5" style={{ background: "var(--surface-2)" }}>{N.topics[a.topic] ?? "기타"}</span>
          </div>
          <a href={a.link} target="_blank" rel="noreferrer" className="mt-1 block text-[14px] font-semibold underline-offset-2 hover:underline">{a.title}</a>
          <div className="mt-1 text-[12px]">
            {a.dir === 0 ? <span style={{ color: "var(--ink-3)" }}>판단 유보 · {a.why}</span>
              : <><b style={{ color: a.dir > 0 ? "var(--up)" : "var(--down)" }}>{a.topic === "krw" ? (a.dir > 0 ? "환율 상승 보도" : "환율 하락 보도") : a.dir > 0 ? "원화 약세 압력" : "원화 강세 압력"}</b>
                <span style={{ color: "var(--ink-3)" }}> · 강도 {"●".repeat(a.strength)}{"○".repeat(3 - a.strength)} · {a.why}</span></>}
          </div>
        </div>))}
      {list.length > 60 && <div className="text-center text-[12px]" style={{ color: "var(--ink-3)" }}>상위 60건만 표시</div>}
    </div>
  );
}
