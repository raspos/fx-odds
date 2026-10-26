import { useMemo, useState } from "react";
import EChart, { usePalette } from "./EChart";
import { J, fmt, sgn } from "./../lib";

const clr = (v: number | null) => (v == null ? "var(--ink-3)" : v >= 0 ? "var(--up)" : "var(--down)");

export function Pressure({ P, asOf }: { P: J; asOf: string | null }) {
  const pal = usePalette();
  const H = P.history;
  const idx = useMemo(() => {
    if (!asOf) return H.dates.length - 1;
    let lo = -1; for (let i = 0; i < H.dates.length; i++) { if (H.dates[i] <= asOf) lo = i; else break; } return lo;
  }, [asOf, H]);
  const areas: J[] = P.areas_def.map((a: J) => ({ ...a, p: H[a.id][idx] }));
  const fpi = H.fpi[idx], cov = H.coverage[idx], date = H.dates[idx];
  const nAv = areas.filter((a) => a.p != null).length;
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
    const s = Math.max(0, idx - 500);
    return { animation: false, grid: { left: 8, right: 16, top: 12, bottom: 24, containLabel: true }, tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: H.dates.slice(s, idx + 1), axisLabel: { color: pal.ink3 } }, yAxis: { type: "value", min: -60, max: 60, axisLabel: { color: pal.ink3 }, splitLine: { lineStyle: { color: pal.line } } },
      series: [{ type: "line", showSymbol: false, data: H.fpi.slice(s, idx + 1), lineStyle: { color: pal.ink, width: 1.6 }, markLine: { silent: true, symbol: "none", data: [{ yAxis: 0 }], lineStyle: { color: pal.ink3, type: "dashed" }, label: { show: false } } }] };
  }, [H, idx, pal]);
  const V = P.validation;
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
        <div className="mt-2 text-[12px] num" style={{ color: "var(--ink-3)" }}>전일 대비 {prev == null || fpi == null ? "–" : sgn(fpi - prev, 1)} · 5영업일 전 대비 {wk == null || fpi == null ? "–" : sgn(fpi - wk, 1)} · 자료 충족률 {fmt(cov * 100)}% ({nAv}/10개 영역)</div>
        <div className="relative mt-3 h-3 rounded-full" style={{ background: "linear-gradient(90deg,var(--down),var(--surface-2) 50%,var(--up))" }}>
          {fpi != null && <div className="absolute -top-1 h-5 w-1 rounded" style={{ left: `calc(${(fpi + 100) / 2}% - 2px)`, background: "var(--ink)" }} />}</div>
        <div className="mt-1 flex justify-between text-[11px]" style={{ color: "var(--ink-3)" }}><span>−100 강한 원화 강세 압력</span><span>0</span><span>+100 강한 원화 약세 압력</span></div>
        <p className="mt-3 text-[12px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
          FPI +60은 환율 상승 확률 60%가 아닙니다. 가중치(10개 영역 동일)와 요인 부호를 사람이 정한 규칙 기반 지수이며, <b>아래 검증에서 이후 7·30일 환율과의 관계가 통계적으로 확인되지 않았습니다.</b> 그래서 확률 전망에 반영하지 않습니다.
        </p>
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
        <p className="mt-2 text-[11px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
          요인 신호는 최근 20영업일 변화(월별 자료는 3개월 합)를 과거 {P.z_window}영업일(월별 60개월) 분포로 표준화(±3 절단)해 −100~+100으로 환산합니다. 한국 금리는 미국 2년 금리, 엔·위안·대만 달러는 달러 공통요인을 회귀로 제거한 잔차만 써서 같은 달러 충격이 중복 집계되지 않게 했습니다.
          경상수지·외국인 증권투자는 월별 발표 자료라 발표 시차(월말+41일)를 반영하며 극단값에 쉽게 포화(±100)됩니다. 결측 영역은 0점이 아니라 제외합니다.
        </p>
      </div>
      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">FPI 추이 (최근 2년)</h3>
        <EChart option={tOpt} height={240} />
      </div>
      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">검증: FPI는 이후 환율을 예고했는가 (2012~)</h3>
        <div className="scrollx"><table className="t"><thead><tr><th>기간</th><th>표본</th><th>상관</th><th>HAC t</th><th>부호 적중(전체)</th><th>부호 적중(강한 신호 상위 25%)</th><th>적중(비중첩) / 이항검정 p</th></tr></thead>
          <tbody>{(["h7", "h30"] as const).map((k) => (<tr key={k}><td>{k === "h7" ? "7일 후" : "30일 후"}</td><td className="num">{fmt(V[k].n)}</td><td className="num">{sgn(V[k].corr, 3)}</td><td className="num">{sgn(V[k].t_hac, 2)}</td>
            <td className="num">{(V[k].hit_all * 100).toFixed(1)}%</td><td className="num">{(V[k].hit_strong * 100).toFixed(1)}%</td><td className="num">{(V[k].hit_nonoverlap * 100).toFixed(1)}% / {V[k].p_binom.toFixed(2)}</td></tr>))}</tbody></table></div>
        <p className="mt-2 text-[12px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
          |t| &lt; 2, 적중률 약 50%: 현재 규칙으로는 방향 예측력이 확인되지 않습니다. 연도별 상관도 부호가 일정하지 않습니다. 파라미터를 적합하지 않은 규칙 지수라 look-ahead는 없지만 요인 구성을 사람이 정했기 때문에 완전한 표본 외 검증은 아닙니다. 모든 입력은 기준일에 이미 이용 가능했던 값(available_at ≤ 기준일)입니다.
        </p>
        <p className="mt-2 text-[12px]" style={{ color: "var(--ink-3)" }}><b>미보유 자료</b>: {P.missing.join(" · ")}</p>
      </div>
    </div>
  );
}
