import { useMemo, useState } from "react";
import EChart, { usePalette } from "./EChart";
import { J, fmt, sgn, MODEL_SHORT } from "../lib";

const Src = ({ V }: { V: J }) => (
  <p className="mt-1 text-[11px]" style={{ color: "var(--ink-3)" }}>출처: {V.source} · 관측 기준일 <span className="num">{V.asof}</span> (이용 가능일 {V.available_at}) · 세로 점선은 관측 범위·거래시간 변경일</p>
);

function Tile({ k, v, s, color }: { k: string; v: string; s?: string; color?: string }) {
  return (<div className="tile"><div className="k">{k}</div><div className="v" style={color ? { color } : undefined}>{v}</div>{s && <div className="s">{s}</div>}</div>);
}

export default function Volatility({ V, S, BC }: { V: J; S: J; BC: J }) {
  const P = usePalette();
  const L = V.latest;
  const [cmpHz, setCmpHz] = useState<7 | 30>(30);
  const [cmpSub, setCmpSub] = useState("전체");
  const [bHz, setBHz] = useState<7 | 30>(30);
  const [bReg, setBReg] = useState<"all" | "pre" | "post">("all");
  const [bModel, setBModel] = useState<"C" | "P">("P");

  const brk = (dates: string[]) => V.breaks.filter((b: J) => b.date >= dates[0] && b.date <= dates[dates.length - 1]).map((b: J) => ({
    xAxis: b.date, lineStyle: { type: "dashed", color: P.ink3 }, label: { formatter: b.date === "2024-07-01" ? "2024-07 마감 02:00 연장" : "2026-07 24시간 개시", color: P.ink3, fontSize: 10, position: "insideEndTop" } }));
  const base = { animation: false, grid: { left: 8, right: 12, top: 28, bottom: 28, containLabel: true }, tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { color: P.ink2 } } };
  const xAxis = (d: string[]) => ({ type: "category", data: d, axisLabel: { color: P.ink3 }, axisLine: { lineStyle: { color: P.line } } });
  const yAxis = (name: string, extra: J = {}) => ({ type: "value", name, nameTextStyle: { color: P.ink3 }, axisLabel: { color: P.ink3 }, splitLine: { lineStyle: { color: P.line } }, scale: true, ...extra });

  const o1 = useMemo(() => ({ ...base, legend: undefined, tooltip: { trigger: "axis", axisPointer: { type: "cross" } }, xAxis: xAxis(V.ohlc_recent.dates), yAxis: yAxis("원/달러"),
    series: [{ type: "candlestick", data: V.ohlc_recent.dates.map((_: string, i: number) => [V.ohlc_recent.O[i], V.ohlc_recent.C[i], V.ohlc_recent.L[i], V.ohlc_recent.H[i]]),
      itemStyle: { color: P.up, color0: P.down, borderColor: P.up, borderColor0: P.down } }], dataZoom: [{ type: "inside" }] }), [V, P]);
  const o2 = useMemo(() => ({ ...base, legend: undefined, xAxis: xAxis(V.range_1y.dates), yAxis: yAxis("일중 변동폭(원)", { scale: false }),
    series: [{ type: "bar", data: V.range_1y.range_won, itemStyle: { color: P.ink3, opacity: 0.75 }, markLine: { silent: true, symbol: "none", data: brk(V.range_1y.dates) } }] }), [V, P]);
  const o3 = useMemo(() => ({ ...base, xAxis: xAxis(V.range_1y.dates), yAxis: yAxis("평균 일중 변동폭(원)", { scale: false }),
    series: [["avg5", "5일", P.up], ["avg20", "20일", P.ink], ["avg60", "60일", P.down]].map(([k, n, c], i) => ({ name: n as string, type: "line", showSymbol: false, data: V.range_1y[k as string], lineStyle: { width: 1.6, color: c as string },
      markLine: i === 0 ? { silent: true, symbol: "none", data: brk(V.range_1y.dates) } : undefined })) }), [V, P]);
  const o4 = useMemo(() => ({ ...base, legend: undefined, xAxis: xAxis(V.fxvi_3y.dates), yAxis: yAxis("FXVI", { min: 0, max: 100, scale: false }),
    series: [{ type: "line", showSymbol: false, connectNulls: false, data: V.fxvi_3y.fxvi, lineStyle: { color: P.ink, width: 1.6 }, areaStyle: { color: P.ink3, opacity: 0.1 },
      markLine: { silent: true, symbol: "none", data: [...brk(V.fxvi_3y.dates), { yAxis: 50, lineStyle: { color: P.line, type: "dotted" }, label: { show: false } }] } }] }), [V, P]);
  const o5 = useMemo(() => ({ ...base, xAxis: xAxis(V.level_vs_vol.dates), yAxis: [yAxis("원/달러(매매기준율)"), yAxis("20일 파킨슨 변동성(연율 %)", { splitLine: { show: false } })],
    series: [{ name: "환율(왼쪽)", type: "line", showSymbol: false, data: V.level_vs_vol.fix, lineStyle: { color: P.ink, width: 1.5 }, markLine: { silent: true, symbol: "none", data: brk(V.level_vs_vol.dates) } },
      { name: "변동성(오른쪽)", type: "line", yAxisIndex: 1, showSymbol: false, data: V.level_vs_vol.park20_ann, lineStyle: { color: P.up, width: 1.5 } }] }), [V, P]);
  const yrs = V.yearly.filter((y: J) => y.n > 60);
  const o6 = useMemo(() => ({ ...base, legend: undefined, xAxis: xAxis(yrs.map((y: J) => String(y.year))), yAxis: yAxis("평균 일중 변동폭(원)", { scale: false }),
    tooltip: { trigger: "axis", formatter: (p: J) => { const y = yrs[p[0].dataIndex]; return `${y.year}년 · ${y.n}세션<br/>평균 변동폭 ${y.mean_range_won}원 · 중앙 변동률 ${y.median_range_pct}%${y.year === 2024 ? "<br/>(7월 마감 연장 전후 혼합)" : y.year > 2024 ? "<br/>(연장된 관측 범위)" : ""}`; } },
    series: [{ type: "bar", data: yrs.map((y: J) => ({ value: y.mean_range_won, itemStyle: { color: y.year < 2024 ? P.ink3 : y.year === 2024 ? P.down : P.up, opacity: 0.85 } })) }] }), [V, P]);

  const cmpRows = S.vol_comparison.filter((r: J) => r.horizon === cmpHz && r.subset === cmpSub);
  const subsets: string[] = [...new Set<string>(S.vol_comparison.filter((r: J) => r.horizon === cmpHz).map((r: J) => r.subset))];
  const bestCrps = Math.min(...cmpRows.filter((r: J) => r.model !== "PR").map((r: J) => r.crps_pct));
  const bt = BC.tables.find((t: J) => t.hz === bHz && t.model === bModel && t.regime === bReg);
  const bs = BC.summary.find((t: J) => t.hz === bHz && t.model === bModel && t.regime === bReg);
  const oCal = useMemo(() => bt ? ({ ...base, legend: undefined, tooltip: { trigger: "item", formatter: (p: J) => `예측 ${(p.value[0] * 100).toFixed(1)}% → 관측 ${(p.value[1] * 100).toFixed(1)}%` },
    xAxis: { type: "value", name: "예측 돌파 확률(보정)", min: 0, max: 1, axisLabel: { color: P.ink3, formatter: (v: number) => `${Math.round(v * 100)}%` }, splitLine: { lineStyle: { color: P.line } } },
    yAxis: { type: "value", name: "관측 돌파 빈도", min: 0, max: 1, axisLabel: { color: P.ink3, formatter: (v: number) => `${Math.round(v * 100)}%` }, splitLine: { lineStyle: { color: P.line } } },
    series: [{ type: "line", data: [[0, 0], [1, 1]], showSymbol: false, silent: true, lineStyle: { type: "dashed", color: P.ink3 } },
      { type: "line", data: bt.bins.map((b: J) => [b.pred_bridge, b.obs]), symbolSize: 9, lineStyle: { color: P.up, width: 2 }, itemStyle: { color: P.up } }] }) : {}, [bt, P]);

  const fx = L.fxvi;
  const fxColor = fx == null ? undefined : fx >= 75 ? P.up : fx <= 25 ? P.down : undefined;
  return (
    <div className="space-y-4">
      <div className="card p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2 text-[12px]" style={{ color: "var(--ink-3)" }}>
          <span className="rounded-full px-2 py-0.5 text-xs font-bold" style={{ background: "var(--warn-bg)", color: "var(--warn-ink)" }}>과거 실현 변동성 지수 · 옵션 내재변동성(VIX형) 아님</span>
          <span className="num">최근 완결 세션 {L.date} · 이용 가능 {V.available_at} · {L.regime}</span>
        </div>
        <div className="tiles">
          <Tile k="최신 일중 최고가" v={`${fmt(L.H, 1)}`} s={`시가 ${fmt(L.O, 1)} · 종가 ${fmt(L.C, 1)}`} />
          <Tile k="최신 일중 최저가" v={`${fmt(L.L, 1)}`} s="원/달러" />
          <Tile k="일중 변동폭(원)" v={`${fmt(L.range_won, 1)}원`} s={`5·20·60일 평균 ${fmt(L.avg5, 1)} · ${fmt(L.avg20, 1)} · ${fmt(L.avg60, 1)}`} />
          <Tile k="일중 변동률" v={`${fmt(L.range_pct, 2)}%`} s={`20일 파킨슨 ${fmt(L.park20_daily_pct, 2)}%/일 · 연율 ${fmt(L.park20_ann_pct, 1)}%`} />
          <Tile k="FXVI (0~100)" v={fx == null ? "산출 보류" : fmt(fx, 0)} s={fx == null ? L.fxvi_note : "높을수록 최근 변동성이 역사적으로 높음"} color={fxColor} />
          <Tile k="전일 대비 FXVI" v={L.fxvi_change == null ? "–" : sgn(L.fxvi_change, 1)} s={L.fxvi_prev == null ? undefined : `전일 ${fmt(L.fxvi_prev, 1)}`} />
        </div>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-[13px] leading-relaxed">{V.commentary.map((c: string, i: number) => <li key={i}>{c}</li>)}</ul>
        <details className="mt-2"><summary className="cursor-pointer text-[12px] font-semibold" style={{ color: "var(--ink-2)" }}>계산 방법과 한계 (펼치기)</summary>
          <div className="mt-1 space-y-1 text-[12px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
            <p><b>일중 변동폭</b> = 고가 − 저가(원). <b>일중 변동률</b> = (고가−저가) ÷ ((고가+저가)/2) × 100. 일 단위 값이라 거래 시간이 길어지면 커지는 경향이 있습니다.</p>
            <p><b>20일 파킨슨 변동성</b>: {V.definition.parkinson}.</p>
            <p><b>FXVI</b>: {V.definition.fxvi}</p>
            <p><b>레짐 처리</b>: 관측 범위가 달라진 날({V.breaks.map((b: J) => b.date).join(", ")})이 있어, 백분위는 같은 레짐 안 252거래일로만 계산하고 부족하면 산출하지 않습니다. 2026-07-06 전후 단절 검정: 일중 변동률 중앙값 {V.regime_test_2026_07_06.median_pre}% → {V.regime_test_2026_07_06.median_post}%, p={V.regime_test_2026_07_06.p_welch}({V.regime_test_2026_07_06.significant ? "단절 확인, 구간 분리" : "단절 미확인, 같은 구간으로 처리"}).</p>
            <ul className="list-disc pl-5">{V.limits.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            {V.dropped_invalid.length > 0 && <p>원자료 오류로 제외한 날: {V.dropped_invalid.join(", ")}</p>}
          </div>
        </details>
      </div>

      <div className="card p-4 sm:p-5"><h3>① 일별 시가·고가·저가·종가 (최근 120세션)</h3><EChart option={o1} height={280} /><Src V={V} /></div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-4 sm:p-5"><h3>② 최근 1년 일중 변동폭</h3><EChart option={o2} height={240} /><Src V={V} /></div>
        <div className="card p-4 sm:p-5"><h3>③ 5·20·60일 평균 변동폭</h3><EChart option={o3} height={240} /><Src V={V} /></div>
      </div>
      <div className="card p-4 sm:p-5"><h3>④ FXVI 최근 3년</h3><EChart option={o4} height={260} />
        <p className="text-[12px]" style={{ color: "var(--ink-3)" }}>끊긴 구간은 같은 관측 구간의 기초 자료(252거래일)가 부족해 산출하지 않은 기간입니다. 2024-07 이전과 이후의 값은 서로 다른 분포 기준이라 이어서 비교하지 않습니다.</p><Src V={V} /></div>
      <div className="card p-4 sm:p-5"><h3>⑤ 환율 수준과 변동성</h3><EChart option={o5} height={260} /><Src V={V} /></div>
      <div className="card p-4 sm:p-5"><h3>⑥ 연도별 평균 일중 변동폭</h3><EChart option={o6} height={240} />
        <p className="text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>회색: 2023년까지(09:00~15:30 중심 관측), 파랑: 2024년(7월 마감 연장 전후 혼합), 주황: 2025년 이후(연장된 관측 범위). 2024-07 이후의 큰 값은 변동성 증가와 관측 범위 확대가 섞여 있어 직접 비교할 수 없습니다.</p><Src V={V} /></div>

      <div className="card p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2"><h3 className="mr-auto">고저가 변동성 모형 vs 기존 모형 (백테스트)</h3>
          {[7, 30].map((h) => <button key={h} className="btn" aria-pressed={cmpHz === h} onClick={() => { setCmpHz(h as 7 | 30); setCmpSub("전체"); }}>{h}일</button>)}</div>
        <div className="mt-2 flex flex-wrap gap-1.5">{subsets.map((sname) => <button key={sname} className="btn" aria-pressed={cmpSub === sname} onClick={() => setCmpSub(sname)}>{sname.split("(")[0]}</button>)}</div>
        <div className="scrollx mt-2"><table className="t"><thead><tr><th>모형</th><th>표본</th><th>CRPS(%)</th><th>로그 점수</th><th>50% 포함</th><th>80% 포함</th><th>90% 포함</th><th>RW 대비</th><th>EWMA 대비</th><th>DM p(vs EWMA)</th></tr></thead>
          <tbody>{cmpRows.map((r: J) => (<tr key={r.model} style={r.model !== "PR" && r.crps_pct === bestCrps ? { background: "var(--surface-2)", fontWeight: 700 } : undefined}>
            <td>{MODEL_SHORT[r.model]}{r.model !== "PR" && r.crps_pct === bestCrps ? " ★" : ""}</td><td className="num">{fmt(r.n)}</td><td className="num">{r.crps_pct.toFixed(4)}</td><td className="num">{r.logscore.toFixed(3)}</td>
            <td className="num">{(r.cov50 * 100).toFixed(1)}%</td><td className="num">{(r.cov80 * 100).toFixed(1)}%</td><td className="num">{(r.cov90 * 100).toFixed(1)}%</td>
            <td className="num">{r.model === "A" ? "기준" : sgn(r.vs_rw_pct, 2) + "%"}</td><td className="num">{r.model === "C" ? "기준" : sgn(r.vs_ewma_pct, 2) + "%"}</td><td className="num">{r.model === "C" ? "–" : r.dm_p_vs_ewma < 0.001 ? "<0.001" : r.dm_p_vs_ewma.toFixed(3)}</td></tr>))}</tbody></table></div>
        <details className="mt-2"><summary className="cursor-pointer text-[12px] font-semibold" style={{ color: "var(--ink-2)" }}>읽는 법 (펼치기)</summary>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-[12px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
            <li>같은 기준일 표본에서 비교합니다. CRPS는 낮을수록, 로그 점수는 <b>높을수록</b> 좋습니다(정규분포 밀도의 로그). 포함률은 50/80/90%에 가까울수록 정직한 구간입니다.</li>
            <li><b>P</b>(파킨슨, 스케일 보정)는 최근 20세션 고저가 분산에 k(밤사이 갭·관측 범위 보정, 직전 250일 기준, 현재 {V.scale_k_latest})를 곱해 씁니다. <b>PR</b>(원시 파킨슨)은 보정 없이 쓴 진단용으로, 구간이 좁게 나옵니다.</li>
            <li>변동성 급등기는 기준일 시점의 20일 변동성이 직전 3년 중 상위 20%인 날(사후가 아니라 사전 정의)입니다.</li>
            <li>새 모형이 더 정확하다고 가정하지 않았습니다. 차이가 DM 검정에서 유의하지 않으면(p&gt;0.05) 개선이 확인되지 않은 것입니다.</li>
          </ul></details>
      </div>

      <div className="card p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2"><h3 className="mr-auto">장벽(기간 중 돌파) 확률 보정 성적표</h3>
          {[7, 30].map((h) => <button key={h} className="btn" aria-pressed={bHz === h} onClick={() => setBHz(h as 7 | 30)}>{h}일</button>)}</div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {([["all", "전체"], ["pre", "2024-07 이전"], ["post", "2024-07 이후"]] as const).map(([k, l]) => <button key={k} className="btn" aria-pressed={bReg === k} onClick={() => setBReg(k)}>{l}</button>)}
          {(["C", "P"] as const).map((m) => <button key={m} className="btn" aria-pressed={bModel === m} onClick={() => setBModel(m)}>{MODEL_SHORT[m]}</button>)}
        </div>
        {bt && bs ? (<>
          <p className="mt-2 text-[13px] leading-relaxed">기준 환율 ±10·20·30원 장벽, 표본 {fmt(bs.n)}건: 평균 예측 돌파 확률 <b className="num">{(bs.mean_pred_bridge * 100).toFixed(1)}%</b>, 관측된 돌파 빈도 <b className="num">{(bs.mean_obs * 100).toFixed(1)}%</b>
            (이산 일별 감시 예측 {(bs.mean_pred_disc * 100).toFixed(1)}%). Brier: 보정 {bs.brier_bridge} · 이산 {bs.brier_disc} (낮을수록 좋음). 만기 시점 확률은 예측 {(bs.mean_end_pred * 100).toFixed(1)}% · 관측 {(bs.mean_end_obs * 100).toFixed(1)}%.</p>
          <EChart option={oCal} height={260} />
          <div className="scrollx"><table className="t"><thead><tr><th>예측 확률 구간</th><th>표본</th><th>평균 예측(보정)</th><th>이산 예측</th><th>관측 빈도</th><th>관측 95% 구간*</th></tr></thead>
            <tbody>{bt.bins.map((b: J, i: number) => (<tr key={i}><td className="num">{(b.lo * 100).toFixed(0)}~{(b.hi * 100).toFixed(0)}%</td><td className="num">{fmt(b.n)}</td><td className="num">{(b.pred_bridge * 100).toFixed(1)}%</td><td className="num">{(b.pred_disc * 100).toFixed(1)}%</td>
              <td className="num font-bold">{(b.obs * 100).toFixed(1)}%</td><td className="num">{b.obs_ci[0] == null ? "–" : `${(b.obs_ci[0] * 100).toFixed(0)}~${(b.obs_ci[1] * 100).toFixed(0)}%`}</td></tr>))}</tbody></table></div>
        </>) : <p className="mt-2 text-sm">표본이 부족해 표시하지 않습니다.</p>}
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
          {BC.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}
          <li>* 겹치는 기준일을 고려해 독립 표본 수를 줄인 윌슨 구간. 관측 빈도는 "관측 범위 안에서 확인된 돌파"의 하한이며, 관측 밖 장중 가격 돌파를 확인했다고 주장하지 않습니다.</li>
        </ul>
      </div>
    </div>
  );
}
