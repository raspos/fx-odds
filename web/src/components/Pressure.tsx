import { useMemo, useState } from "react";
import EChart, { usePalette } from "./EChart";
import { J, fmt, sgn } from "./../lib";

const clr = (v: number | null) => (v == null ? "var(--ink-3)" : v >= 0 ? "var(--up)" : "var(--down)");

export function Pressure({ P, asOf, S }: { P: J; asOf: string | null; S: J }) {
  const pal = usePalette();
  const H = P.history;
  const idx = useMemo(() => {
    if (!asOf) return H.dates.length - 1;
    let lo = -1; for (let i = 0; i < H.dates.length; i++) { if (H.dates[i] <= asOf) lo = i; else break; } return lo;
  }, [asOf, H]);
  const areas: J[] = P.areas_def.map((a: J) => ({ ...a, p: H[a.id][idx] }));
  const fpi = H.fpi[idx], date = H.dates[idx];
  const prev = idx > 0 ? H.fpi[idx - 1] : null, wk = idx >= 5 ? H.fpi[idx - 5] : null;
  const L = P.latest; const live = idx === H.dates.length - 1;
  const comps: Record<string, J[]> = Object.fromEntries(L.areas.map((a: J) => [a.id, a.components]));
  const sorted = [...areas].filter((a) => a.p != null).sort((a, b) => b.p - a.p);
  const opt = useMemo(() => ({
    animation: false, grid: { left: 8, right: 40, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v: number) => (v == null ? "자료 없음" : v.toFixed(1)) },
    xAxis: { type: "value", min: -100, max: 100, axisLabel: { color: pal.ink3 }, splitLine: { lineStyle: { color: pal.line } } },
    yAxis: { type: "category", inverse: true, data: areas.map((a) => a.name), axisLabel: { color: pal.ink } },
    series: [{ type: "bar", data: areas.map((a) => ({ value: a.p, itemStyle: { color: a.p == null ? pal.ink3 : a.p >= 0 ? pal.up : pal.down } })),
      label: { show: true, position: "right", color: pal.ink2, formatter: (p: J) => (p.value == null ? "자료 없음" : sgn(p.value, 0)) } }],
  }), [areas, pal]);
  const tOpt = useMemo(() => {
    const s0 = Math.max(0, idx - 500);
    const dates: string[] = H.dates.slice(s0, idx + 1);
    const fx = new Map<string, number>(S.dates.map((d: string, i: number) => [d, S.usdkrw[i]]));
    let last: number | null = null;
    const krw = dates.map((d) => { const v = fx.get(d); if (v != null) last = v; return last; });
    return { animation: false, grid: { left: 8, right: 8, top: 34, bottom: 24, containLabel: true }, legend: { top: 0, textStyle: { color: pal.ink2 } },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => (v == null ? "–" : v.toFixed(1)) },
      xAxis: { type: "category", data: dates, axisLabel: { color: pal.ink3 } },
      yAxis: [{ type: "value", name: "FPI", min: -60, max: 60, nameTextStyle: { color: pal.ink3 }, axisLabel: { color: pal.ink3 }, splitLine: { lineStyle: { color: pal.line } } },
        { type: "value", name: "원/달러", scale: true, nameTextStyle: { color: pal.ink3 }, axisLabel: { color: pal.ink3 }, splitLine: { show: false } }],
      series: [{ name: "FPI(왼쪽)", type: "line", showSymbol: false, data: H.fpi.slice(s0, idx + 1), lineStyle: { color: pal.up, width: 1.5 },
          markLine: { silent: true, symbol: "none", data: [{ yAxis: 0 }], lineStyle: { color: pal.ink3, type: "dashed" }, label: { show: false } } },
        { name: "원/달러(오른쪽)", type: "line", yAxisIndex: 1, showSymbol: false, data: krw, lineStyle: { color: pal.ink, width: 1.8 } }] };
  }, [H, idx, pal, S]);
  const dir = fpi == null ? "–" : fpi > 5 ? "원화 약세(환율 상승) 압력 우세" : fpi < -5 ? "원화 강세(환율 하락) 압력 우세" : "뚜렷한 방향 없음(중립 부근)";
  return (
    <div className="space-y-4">
      <div className="card p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2"><span className="rounded-full px-2 py-0.5 text-xs font-bold" style={{ background: "var(--warn-bg)", color: "var(--warn-ink)" }}>실험적 압력 지수 · 확률 아님</span>
          <span className="text-xs num" style={{ color: "var(--ink-3)" }}>{date} 기준{!live ? " (과거 자료 재계산)" : ""}</span></div>
        <div className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-1">
          <div className="num text-5xl font-black" style={{ color: clr(fpi) }}>{fpi == null ? "–" : sgn(fpi, 1)}</div>
          <div className="pb-1 text-sm" style={{ color: "var(--ink-2)" }}>{dir}</div>
        </div>
        <div className="mt-2 text-[12px] num" style={{ color: "var(--ink-3)" }}>전일 대비 {prev == null || fpi == null ? "–" : sgn(fpi - prev, 1)} · 5영업일 전 대비 {wk == null || fpi == null ? "–" : sgn(fpi - wk, 1)}</div>
        <div className="relative mt-3 h-3 rounded-full" style={{ background: "linear-gradient(90deg,var(--down),var(--surface-2) 50%,var(--up))" }}>
          {fpi != null && <div className="absolute -top-1 h-5 w-1 rounded" style={{ left: `calc(${(fpi + 100) / 2}% - 2px)`, background: "var(--ink)" }} />}</div>
        <div className="mt-1 flex justify-between text-[11px]" style={{ color: "var(--ink-3)" }}><span>−100 강한 원화 강세 압력</span><span>0</span><span>+100 강한 원화 약세 압력</span></div>
      </div>
      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">10개 요인별 압력</h3>
        <EChart option={opt} height={340} />
        <div className="scrollx">
          <table className="t"><thead><tr><th>요인</th><th>압력</th><th>무엇을 보나</th><th>자료</th></tr></thead>
            <tbody>{areas.map((a) => (<tr key={a.id}><td>{a.name}</td><td className="num" style={{ color: clr(a.p) }}>{a.p == null ? "자료 없음" : sgn(a.p, 1)}</td>
              <td style={{ whiteSpace: "normal", textAlign: "left" }}>{a.desc}</td><td style={{ textAlign: "left" }}>{P.sources[a.id]}</td></tr>))}</tbody></table>
        </div>
        {live && sorted.length > 0 && <p className="mt-2 text-[13px] leading-relaxed">주요 <b style={{ color: "var(--up)" }}>상승(원화 약세) 요인</b>: {sorted.filter((a) => a.p > 0).slice(0, 3).map((a) => `${a.name}(${sgn(a.p, 0)})`).join(", ") || "없음"} · 주요 <b style={{ color: "var(--down)" }}>하락(원화 강세) 요인</b>: {[...sorted].reverse().filter((a) => a.p < 0).slice(0, 3).map((a) => `${a.name}(${sgn(a.p, 0)})`).join(", ") || "없음"}</p>}
      </div>
      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">FPI 추이와 실제 환율 (최근 2년)</h3>
        <EChart option={tOpt} height={300} />
        <p className="text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>FPI(주황)가 올라갈 때 환율(검정)이 뒤따라 오르면 지수가 방향을 짚은 것입니다.</p>
      </div>
    </div>
  );
}
