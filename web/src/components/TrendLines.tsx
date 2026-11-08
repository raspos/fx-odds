import { useMemo } from "react";
import EChart, { usePalette } from "./EChart";
import { J, sgn } from "../lib";

/** 뉴스 압력지수(FSI)와 통계 압력지수(FPI)의 흐름을 각각 선 하나로 보여 준다(아주 단순하게). asOf 가 있으면 그 날짜까지만 쓴다. */
function Line({ title, note, dates, vals, color }: { title: string; note: string; dates: string[]; vals: (number | null)[]; color: string }) {
  const pal = usePalette();
  const last = [...vals].reverse().find((v) => v != null) ?? null;
  const opt = useMemo(() => ({
    grid: { left: 36, right: 12, top: 10, bottom: 24 },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => (v == null ? "–" : sgn(v, 1)) },
    xAxis: { type: "category", data: dates, boundaryGap: false, axisLabel: { color: pal.ink3, fontSize: 10, formatter: (d: string) => d.slice(5) }, axisLine: { lineStyle: { color: pal.line } } },
    yAxis: { type: "value", axisLabel: { color: pal.ink3, fontSize: 10 }, splitLine: { lineStyle: { color: pal.line } } },
    series: [{ type: "line", data: vals, showSymbol: dates.length < 40, symbolSize: 5, connectNulls: true, lineStyle: { color, width: 2 }, itemStyle: { color },
      markLine: { silent: true, symbol: "none", data: [{ yAxis: 0 }], lineStyle: { color: pal.ink3, type: "dashed" }, label: { show: false } } }],
  }), [dates, vals, pal, color]);
  return (
    <div className="card p-4">
      <div className="flex items-baseline gap-2"><h3 className="mr-auto text-[15px] font-bold">{title}</h3>
        <span className="num text-lg font-black" style={{ color: last == null ? "var(--ink-3)" : last >= 0 ? "var(--up)" : "var(--down)" }}>{last == null ? "–" : sgn(last, 1)}</span></div>
      {dates.length < 2 ? <p className="mt-2 text-[12px]" style={{ color: "var(--ink-3)" }}>기록이 쌓이는 중입니다.</p> : <EChart option={opt} height={180} />}
      <p className="text-[11px]" style={{ color: "var(--ink-3)" }}>{note}</p>
    </div>
  );
}

export function TrendLines({ snap, fpi, asOf }: { snap?: J; fpi: J; asOf: string | null }) {
  const pal = usePalette();
  const sd: string[] = [], sv: (number | null)[] = [];
  (snap?.dates ?? []).forEach((d: string, i: number) => { if ((!asOf || d <= asOf) && snap.npi?.[i] != null) { sd.push(d); sv.push(snap.npi[i]); } });
  const H = fpi.history; const n = 90;
  let end = H.dates.length; if (asOf) end = H.dates.filter((d: string) => d <= asOf).length;
  const fd: string[] = H.dates.slice(Math.max(0, end - n), end), fv: (number | null)[] = H.fpi.slice(Math.max(0, end - n), end);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Line title="뉴스 압력지수(FSI) 흐름" note="매일 한 번 기록한 값(10/27~). 매체를 47곳으로 제한하기 전 값은 전체 매체 기준이라 수준이 다를 수 있습니다. 확률 아님." dates={sd} vals={sv} color={pal.up || "#f24822"} />
      <Line title="통계 압력지수(FPI) 흐름" note="최근 90영업일. 0 위는 원화 약세, 아래는 원화 강세 압력. 확률 아님." dates={fd} vals={fv} color={pal.down || "#0d99ff"} />
    </div>
  );
}
