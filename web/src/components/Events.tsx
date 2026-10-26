import { useState } from "react";
import { J } from "../lib";

const DIR: Record<string, string> = { krw_weak: "var(--up)", krw_strong: "var(--down)", mixed: "var(--ink-3)" };

export function Events({ E, asOf, refDate }: { E: J; asOf: string | null; refDate: string }) {
  const [win, setWin] = useState<1 | 7 | 30>(30);
  const [cat, setCat] = useState<string>("all");
  const day = (d: string) => new Date(d + "T00:00:00Z").getTime() / 86400000;
  const list: J[] = E.events.filter((e: J) => {
    if (asOf && e.available_at > asOf) return false; // 당시 확인 가능했던 사건만
    const age = day(refDate) - day(e.date);
    return age >= 0 && age <= win && (cat === "all" || e.cats.includes(cat));
  });
  return (
    <div className="space-y-4">
      <div className="card p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="mr-auto text-lg font-bold">시장 사건 타임라인</h3>
          {([1, 7, 30] as const).map((w) => <button key={w} className="btn" aria-pressed={win === w} onClick={() => setWin(w)}>{w === 1 ? "24시간" : `${w}일`}</button>)}
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button className="btn" aria-pressed={cat === "all"} onClick={() => setCat("all")}>전체</button>
          {Object.entries(E.cats).map(([k, v]) => <button key={k} className="btn" aria-pressed={cat === k} onClick={() => setCat(k)}>{v as string}</button>)}
        </div>
        <p className="mt-3 rounded-lg p-3 text-[12px] leading-relaxed" style={{ background: "var(--warn-bg)", color: "var(--warn-ink)" }}>{E.note}</p>
      </div>
      {list.length === 0 && <div className="card p-4 text-sm" style={{ color: "var(--ink-3)" }}>선택한 기간·분류에 해당하는 사건이 없습니다.</div>}
      {list.map((e) => (
        <div key={e.id} className="card p-4">
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: "var(--ink-3)" }}>
            <span className="num">{e.date}</span><span>· 이용 가능 {e.available_at}</span>
            {e.cats.map((c: string) => <span key={c} className="rounded-full px-2 py-0.5" style={{ background: "var(--surface-2)" }}>{E.cats[c]}</span>)}
            {e.n_members > 1 && <span>· 사건 그룹({e.n_members}건 묶음)</span>}
          </div>
          <div className="mt-1 text-[15px] font-bold">{e.title}</div>
          <div className="mt-1 text-[13px]"><b style={{ color: DIR[e.direction] }}>{e.direction_note}</b> · 강도 {"●".repeat(e.strength)}{"○".repeat(3 - e.strength)}</div>
          <p className="mt-1 text-[13px] leading-relaxed" style={{ color: "var(--ink-2)" }}>{e.why}</p>
          <p className="mt-1 text-[11px]" style={{ color: "var(--ink-3)" }}>원인: {e.cause} · 예상 대비: {e.expected_vs_actual} · 출처: {e.sources.map((s: J, i: number) => (<a key={i} href={s.url} target="_blank" rel="noreferrer" className="underline">{s.name}</a>)).reduce((a: J, b: J) => [a, " · ", b])}</p>
        </div>
      ))}
    </div>
  );
}
