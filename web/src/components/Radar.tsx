import { useMemo, useState } from "react";
import EChart, { usePalette } from "./EChart";
import { J, fmt, sgn, fisher, MODEL_SHORT } from "../lib";

const CCY = ["JPY", "CNY", "TWD"] as const;
const NAME: Record<string, string> = { JPY: "엔화", CNY: "위안화", TWD: "대만 달러" };
const WINDOWS = [20, 60, 120, 252];

type Row = { ccy: string; name: string; simple: number | null; partial: number | null; n: number; simple_ci: (number | null)[]; partial_ci: (number | null)[]; simple_chg_1m: number | null; partial_chg_1m: number | null };

/** 날짜 선택 시: 히스토리 배열에서 해당 시점 값을 꺼내 표 행을 다시 만든다(그 날짜까지의 자료만 사용된 이동상관). */
function rowsAt(V: J, w: number, asOfIdx: number | null): { rows: Row[]; date: string } {
  if (asOfIdx == null) return { rows: V.snapshot[String(w)].rows, date: V.last_date };
  const H = V.history;
  const rows = CCY.map((c) => {
    const s = H.series[`${c}_simple_${w}`], p = H.series[`${c}_partial_${w}`];
    const g = (a: (number | null)[], i: number) => (i >= 0 ? a[i] : null);
    const sn = g(s, asOfIdx), pn = g(p, asOfIdx), sp = g(s, asOfIdx - 21), pp = g(p, asOfIdx - 21);
    return { ccy: c, name: NAME[c], simple: sn, partial: pn, n: w,
      simple_ci: sn == null ? [null, null] : fisher(sn, w), partial_ci: pn == null ? [null, null] : fisher(pn, w, 1),
      simple_chg_1m: sn != null && sp != null ? sn - sp : null, partial_chg_1m: pn != null && pp != null ? pn - pp : null };
  });
  return { rows, date: H.dates[asOfIdx] };
}

export default function Radar({ R, asOf }: { R: J; asOf: string | null }) {
  const [w, setW] = useState(60);
  const [kind, setKind] = useState<"simple" | "partial">("simple");
  const [sc, setSc] = useState<(typeof CCY)[number]>("JPY");
  const [llPeriod, setLlPeriod] = useState<"y1" | "y3" | "stress" | "calm">("y3");
  const [llDir, setLlDir] = useState<"lead" | "rev">("lead");
  const V = R.YAHOO;
  const P = usePalette();

  const asOfIdx = useMemo(() => {
    if (!asOf) return null;
    const d: string[] = V.history.dates; let lo = -1;
    const av: string[] = V.history.avail; for (let i = 0; i < d.length; i++) { if (av[i] <= asOf) lo = i; else break; }
    return lo;
  }, [asOf, V]);
  const unavailable = asOfIdx != null && asOfIdx < 252;
  const { rows, date } = rowsAt(V, w, unavailable ? null : asOfIdx);
  const sorted = [...rows].sort((a, b) => (b.simple ?? -9) - (a.simple ?? -9));
  const top = sorted[0];
  const colors: Record<string, string> = { JPY: P.up, CNY: P.down, TWD: P.ink2 };

  const rankOpt = useMemo(() => ({
    animation: false, grid: { left: 8, right: 24, top: 28, bottom: 8, containLabel: true },
    legend: { top: 0, textStyle: { color: P.ink2 } },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "value", min: -0.2, max: 1, axisLabel: { color: P.ink3 }, splitLine: { lineStyle: { color: P.line } } },
    yAxis: { type: "category", inverse: true, data: sorted.map((r) => r.name), axisLabel: { color: P.ink } },
    series: [
      { name: "단순 상관", type: "bar", data: sorted.map((r) => r.simple), itemStyle: { color: P.ink }, label: { show: true, position: "right", color: P.ink2, formatter: (p: J) => sgn(p.value) } },
      { name: "달러 요인 통제 후", type: "bar", data: sorted.map((r) => r.partial), itemStyle: { color: P.ink3, opacity: 0.6 }, label: { show: true, position: "right", color: P.ink2, formatter: (p: J) => sgn(p.value) } },
    ],
  }), [sorted, P]);

  const tsOpt = useMemo(() => {
    const H = V.history; const end = asOfIdx != null && !unavailable ? asOfIdx : H.dates.length - 1;
    const start = Math.max(0, end - 756);
    const x = H.dates.slice(start, end + 1);
    return {
      animation: false, grid: { left: 8, right: 16, top: 30, bottom: 28, containLabel: true },
      legend: { top: 0, textStyle: { color: P.ink2 } },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => (v == null ? "–" : v.toFixed(2)) },
      xAxis: { type: "category", data: x, axisLabel: { color: P.ink3 }, axisLine: { lineStyle: { color: P.line } } },
      yAxis: { type: "value", min: -0.6, max: 1, axisLabel: { color: P.ink3 }, splitLine: { lineStyle: { color: P.line } } },
      dataZoom: [{ type: "inside" }],
      series: CCY.map((c) => ({ name: NAME[c], type: "line", showSymbol: false, lineStyle: { width: 1.6, color: colors[c] }, itemStyle: { color: colors[c] },
        data: H.series[`${c}_${kind}_${w}`].slice(start, end + 1),
        markLine: c === "JPY" ? { silent: true, symbol: "none", lineStyle: { color: P.ink3, type: "dashed" }, data: [{ yAxis: 0 }], label: { show: false } } : undefined })),
    };
  }, [V, asOfIdx, unavailable, kind, w, P]);

  const S = V.scatter[sc];
  const scOpt = useMemo(() => {
    const xs: number[] = S.x; const xmin = Math.min(...xs), xmax = Math.max(...xs);
    return {
      animation: false, grid: { left: 8, right: 16, top: 16, bottom: 36, containLabel: true },
      tooltip: { formatter: (p: J) => `${S.dates[p.dataIndex]}<br/>${NAME[sc]} ${p.value[0].toFixed(2)}% · 원화 ${p.value[1].toFixed(2)}%` },
      xAxis: { type: "value", name: `${NAME[sc]} 일별 수익률(%)`, nameLocation: "middle", nameGap: 24, nameTextStyle: { color: P.ink3 }, axisLabel: { color: P.ink3 }, splitLine: { lineStyle: { color: P.line } } },
      yAxis: { type: "value", name: "원화 수익률(%)", nameTextStyle: { color: P.ink3 }, axisLabel: { color: P.ink3 }, splitLine: { lineStyle: { color: P.line } } },
      series: [
        { type: "scatter", symbolSize: 7, itemStyle: { color: colors[sc], opacity: 0.75 }, data: S.x.map((x: number, i: number) => [x, S.y[i]]) },
        { type: "line", showSymbol: false, silent: true, lineStyle: { color: P.ink, width: 1.5 }, data: [[xmin, S.intercept + S.slope * xmin], [xmax, S.intercept + S.slope * xmax]] },
      ],
    };
  }, [S, sc, P]);

  const LL = V.leadlag;
  const lags = llDir === "lead" ? ["0", "1", "2", "3", "5"] : ["1", "2", "3", "5"];
  const hmOpt = useMemo(() => {
    const data: number[][] = [];
    CCY.forEach((c, i) => lags.forEach((l, j) => data.push([j, i, LL[c][llPeriod][llDir][l]])));
    return {
      animation: false, grid: { left: 8, right: 8, top: 8, bottom: 52, containLabel: true },
      tooltip: { formatter: (p: J) => `${NAME[CCY[p.value[1]]]} · ${llDir === "lead" ? "해외통화가" : "원화가"} ${lags[p.value[0]]}거래일 앞섬<br/>상관 ${p.value[2] == null ? "–" : p.value[2].toFixed(3)}` },
      xAxis: { type: "category", data: lags.map((l) => (l === "0" ? "동시" : `${l}일`)), axisLabel: { color: P.ink2 }, splitArea: { show: false } },
      yAxis: { type: "category", inverse: true, data: CCY.map((c) => NAME[c]), axisLabel: { color: P.ink } },
      visualMap: { min: -0.5, max: 0.5, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemHeight: 140, textStyle: { color: P.ink3 },
        inRange: { color: [P.down, "#e8e7e1", P.up] }, text: ["양(+)", "음(−)"] },
      series: [{ type: "heatmap", data, label: { show: true, color: "#111", formatter: (p: J) => (p.value[2] == null ? "" : p.value[2].toFixed(2)) } }],
    };
  }, [LL, llPeriod, llDir, P]);

  const ci = top?.simple_ci;
  return (
    <div className="space-y-4">
      <div className="card p-4 sm:p-5">
        <details><summary className="cursor-pointer text-[12px] font-semibold" style={{ color: "var(--ink-2)" }}>자료·계산 기준 (펼치기) — 마지막 관측일 <span className="num">{V.last_date}</span></summary>
        <p className="text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
          자료: Yahoo Finance 일봉 마감(비공식) 단일 출처. 원·엔·위안·대만 달러가 같은 시각(런던 자정 마감)에 관측돼 시각 불일치가 없습니다. 자료 마지막 관측일 <b className="num">{V.last_date}</b>, 표본 {fmt(V.n_obs)}일.
          모든 계산은 가격 수준이 아닌 일별 로그수익률(USD 1단위당 외화, 상승=외화 약세) 기준입니다. 전망 모형의 기준 환율(한국은행 ECOS 매매기준율)과는 관측 시각·출처가 달라 일 단위 값이 다를 수 있습니다.
        </p>
        </details>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">창</span>
          {WINDOWS.map((x) => <button key={x} className="btn" aria-pressed={w === x} onClick={() => setW(x)}>{x}거래일</button>)}
        </div>
        {asOfIdx != null && !unavailable && <p className="mt-2 text-[12px]" style={{ color: "var(--warn-ink)" }}>당시 확인 가능했던 마지막 관측: {V.history.dates[asOfIdx]} (이 자료가 공개된 날 {V.history.avail[asOfIdx]} ≤ 선택일 {asOf}).</p>}
        {unavailable && <p className="mt-2 text-sm" style={{ color: "var(--warn-ink)" }}>선택한 날짜는 이동상관 이력(2016년 이후, 첫 252영업일 이후)이 없어 최신 값을 표시합니다.</p>}
      </div>

      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">① 동조화 순위 · {date} 기준 최근 {w}거래일</h3>
        <div className="scrollx mt-2">
          <table className="t">
            <thead><tr><th>비교 통화</th><th>{w}일 상관계수</th><th>95% 신뢰구간</th><th>달러 요인 통제 후</th><th>한 달 전 대비(단순)</th></tr></thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr key={r.ccy} style={i === 0 ? { background: "var(--surface-2)", fontWeight: 700 } : undefined}>
                  <td>{i === 0 ? "▲ " : ""}{r.name}</td><td className="num">{sgn(r.simple)}</td>
                  <td className="num">{r.simple_ci[0] == null ? "–" : `${sgn(r.simple_ci[0])} ~ ${sgn(r.simple_ci[1])}`}</td>
                  <td className="num">{sgn(r.partial)}</td><td className="num">{sgn(r.simple_chg_1m)}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
        <EChart option={rankOpt} height={190} />
        {V.snapshot[String(w)].dxy.simple != null && (() => { const d = V.snapshot[String(w)].dxy; return (
          <div className="mt-2 rounded-lg p-3 text-[12px] leading-relaxed" style={{ background: "var(--surface-2)" }}>
            <b>참고: 달러 인덱스(DXY)와 원화의 {w}일 상관 {sgn(d.simple)}</b> (95% 신뢰구간 {sgn(d.ci[0])}~{sgn(d.ci[1])}, 한 달 전 대비 {sgn(d.chg_1m)}).
            DXY는 유로 57.6%·엔 13.6%·파운드 11.9% 등으로 구성돼 엔화가 포함되므로, 엔화와의 비교에 DXY를 통제변수로 쓰면 엔화 효과가 일부 제거됩니다(DXY와 엔화 상관 {sgn(d.jpy_corr)}).
            그래서 통제에는 한·일·중·대만을 뺀 자체 달러 요인을 쓰고, DXY는 참고용으로 보여 줍니다(자체 요인과 DXY의 상관 {sgn(d.factor_corr)}).
          </div>); })()}
        {ci && ci[0] != null && ci[0] <= 0 && <p className="text-[12px]" style={{ color: "var(--warn-ink)" }}>※ 1위 통화의 신뢰구간이 0을 포함합니다. 순위 차이가 표본 변동일 수 있습니다.</p>}
        <p className="mt-1 text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
          가장 높은 상관계수가 곧 가장 큰 인과적 영향을 뜻하지 않습니다. 달러 요인 통제 후 값은 6개 비아시아 통화(EUR·GBP·AUD·CAD·CHF·SEK)로 만든 공통 달러 요인의 영향을 뺀 부분상관계수입니다.
        </p>
      </div>

      <div className="card p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="mr-auto text-lg font-bold">② 이동상관계수 (최근 3년)</h3>
          <button className="btn" aria-pressed={kind === "simple"} onClick={() => setKind("simple")}>단순</button>
          <button className="btn" aria-pressed={kind === "partial"} onClick={() => setKind("partial")}>달러 요인 통제</button>
        </div>
        <EChart option={tsOpt} height={300} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="mr-auto text-lg font-bold">③ 일별 수익률 산점도</h3>
            {CCY.map((c) => <button key={c} className="btn" aria-pressed={sc === c} onClick={() => setSc(c)}>{NAME[c]}</button>)}
          </div>
          <EChart option={scOpt} height={260} />
          <p className="text-[12px] num" style={{ color: "var(--ink-3)" }}>최근 60거래일({S.dates[0]}~{S.dates[S.dates.length - 1]}) · 상관 {sgn(S.r)} · 기울기 {sgn(S.slope)} · R² {fmt(S.r2, 2)}{asOf ? " · (날짜 선택과 무관하게 최신 구간)" : ""}</p>
        </div>
        <div className="card p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-1.5">
            <h3 className="mr-auto text-lg font-bold">④ 선행·후행 히트맵</h3>
            <button className="btn" aria-pressed={llDir === "lead"} onClick={() => setLlDir("lead")}>해외→원화</button>
            <button className="btn" aria-pressed={llDir === "rev"} onClick={() => setLlDir("rev")}>원화→해외</button>
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {([["y1", "최근 1년"], ["y3", "최근 3년"], ["stress", "불안기(3년 중)"], ["calm", "평시(3년 중)"]] as const).map(([k, l]) => <button key={k} className="btn" aria-pressed={llPeriod === k} onClick={() => setLlPeriod(k)}>{l}</button>)}
          </div>
          <EChart option={hmOpt} height={230} />
          <p className="text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
            {llDir === "lead" ? "원화 수익률(t)과 해외 통화 수익률(t−k)의 상관." : "해외 통화 수익률(t)과 원화 수익률(t−k)의 상관."} 불안기는 원화 20일 변동성 상위 25% 구간.
            {" '동시'는 같은 날 같은 시각에 관측된 마감 간 상관입니다."} 최신 기준 값이며 날짜 선택을 반영하지 않습니다.
          </p>
          <div className="scrollx mt-2">
            <table className="t">
              <thead><tr><th>Granger p (해외→원화)</th>{[1, 2, 3, 4, 5].map((l) => <th key={l}>{l}일</th>)}</tr></thead>
              <tbody>{CCY.map((c) => (<tr key={c}><td>{NAME[c]}</td>{[1, 2, 3, 4, 5].map((l) => {
                const p = V.granger[c].x_to_krw[String(l)]; return <td key={l} className="num" style={p != null && p < 0.05 ? { fontWeight: 700 } : undefined}>{p == null ? "–" : p.toFixed(3)}</td>; })}</tr>))}</tbody>
            </table>
          </div>
          <p className="mt-1 text-[11px]" style={{ color: "var(--ink-3)" }}>Granger 검정은 경제학적 인과가 아니라 "과거 값이 예측 정보를 더하는가"만 봅니다. 15개 검정을 동시에 보므로 5% 미만(굵게)이 우연일 수 있습니다.</p>
        </div>
      </div>

      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">⑤ 예측 기여도 — 이 통화를 넣으면 실제로 더 잘 맞히는가</h3>
        <details className="mt-1"><summary className="cursor-pointer text-[12px] font-semibold" style={{ color: "var(--ink-2)" }}>검증 방법 (펼치기)</summary>
        <p className="mt-1 text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
          Walk-forward(2012~): 원·달러 단독 모형(과거 5·20일 수익률 릿지)과 각 통화의 과거 5·20일 수익률을 추가한 모형의 CRPS를 비교합니다. 해외 통화는 서울 기준일 직전 영업일 마감까지만 사용, 계수는 목표일이 기준일 이전인 표본으로만 추정.
          양(+)은 단독 모형보다 개선, 음(−)은 악화. p값은 Newey-West HAC 보정 Diebold-Mariano 검정입니다.
        </p>
        </details>
        <div className="scrollx mt-2">
          <table className="t">
            <thead><tr><th>추가 변수</th><th>7일 CRPS 개선</th><th>7일 p</th><th>30일 CRPS 개선</th><th>30일 p</th><th>30일 방향 적중</th></tr></thead>
            <tbody>
              {(["JPY", "CNY", "TWD", "ALL3", "ALL3+FACTOR", "RATES", "FPI"] as const).map((k) => {
                const a = R.contribution[k].h7, b = R.contribution[k].h30;
                const lab = k === "RATES" ? "세 통화+달러요인+한미 금리차(F)" : k === "FPI" ? "압력지수(FPI)" : k === "ALL3" ? "세 통화 모두" : k === "ALL3+FACTOR" ? "세 통화 + 달러요인" : NAME[k];
                return (<tr key={k}><td>{lab}</td>
                  <td className="num">{a ? sgn(a.vs_e0_pct, 2) + "%" : "–"}</td><td className="num">{a ? a.p.toFixed(3) : "–"}</td>
                  <td className="num">{b ? sgn(b.vs_e0_pct, 2) + "%" : "–"}</td><td className="num">{b ? b.p.toFixed(3) : "–"}</td>
                  <td className="num">{b ? `${(b.hit * 100).toFixed(1)}% (단독 ${(b.hit_e0 * 100).toFixed(1)}%)` : "–"}</td></tr>);
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-1 text-[11px]" style={{ color: "var(--ink-3)" }}>'세 통화+달러요인+한미 금리차' 행이 금리를 통제한 조건부 모형(F)입니다(국고채 3년 − 미국 5년 금리의 5·20일 변화).</p>
      </div>

      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">⑥ 현재 동조화 해설</h3>
        <p className="mt-1 text-[11px]" style={{ color: "var(--ink-3)" }}>계산 결과로 자동 생성한 규칙 기반 문장입니다(LLM 미사용). 최신 {V.last_date}.</p>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[14px] leading-relaxed">
          {V.narrative.map((s: string, i: number) => <li key={i}>{s}</li>)}
        </ul>
      </div>

      <details className="card p-4 text-[12px] leading-relaxed sm:p-5" style={{ color: "var(--ink-2)" }}>
        <summary className="cursor-pointer text-[13px] font-semibold">공통 달러 요인의 한계 (펼치기)</summary>
        <b>공통 달러 요인의 한계.</b> 요인은 EUR·GBP·AUD·CAD·CHF·SEK의 USD당 로그수익률 단순평균으로, 한·일·중·대만 통화를 포함하지 않아 기계적 중복은 없습니다. 다만 유럽·원자재 통화 편향이 있고, 일반 달러인덱스(DXY)는 엔화를 포함(13.6%)하므로 쓰지 않았습니다. 요인과 원화의 상관은 {sgn(V.snapshot[String(w)].krw_vs_factor)}입니다.
        {" "}<b>예측 기여도</b>는 {Object.keys(MODEL_SHORT).filter((k) => k.startsWith("E")).map((k) => MODEL_SHORT[k]).join(", ")} 모형의 비교입니다.
      </details>
    </div>
  );
}
