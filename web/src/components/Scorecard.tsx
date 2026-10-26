import { useMemo, useState } from "react";
import EChart, { usePalette } from "./EChart";
import { J, fmt, sgn, MODEL_SHORT } from "../lib";

const COLORS: Record<string, string> = { A: "#7a7974", B: "#2a78d6", C: "#eb6834", D: "#2f9e6b" };

export default function Scorecard({ S, base }: { S: J; base: string }) {
  const [hz, setHz] = useState<7 | 30>(30);
  const [period, setPeriod] = useState<"all" | "recent3y">("all");
  const P = usePalette();
  const rows: J[] = S[period].filter((r: J) => r.horizon === hz);
  const official = rows.filter((r) => "ABCD".includes(r.model));
  const cond = rows.filter((r) => !"ABCD".includes(r.model));
  const best = [...official].sort((a, b) => a.crps_pct - b.crps_pct)[0];
  const rw = rows.find((r) => r.model === "A");
  const yearly = S.yearly.filter((y: J) => y.horizon === hz);
  const years = [...new Set<number>(yearly.map((y: J) => y.year))].sort();
  const opt = useMemo(() => ({
    animation: false, grid: { left: 8, right: 16, top: 30, bottom: 24, containLabel: true }, legend: { top: 0, textStyle: { color: P.ink2 } },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => v.toFixed(3) + "%" },
    xAxis: { type: "category", data: years, axisLabel: { color: P.ink3 } },
    yAxis: { type: "value", name: "평균 CRPS(%, 낮을수록 좋음)", nameTextStyle: { color: P.ink3 }, axisLabel: { color: P.ink3 }, splitLine: { lineStyle: { color: P.line } } },
    series: ["A", "B", "C", "D"].map((m) => ({ name: MODEL_SHORT[m], type: "line", showSymbol: false, lineStyle: { color: COLORS[m], width: 2 },
      itemStyle: { color: COLORS[m] }, data: years.map((y) => yearly.find((r: J) => r.year === y && r.model === m)?.crps_pct ?? null) })),
  }), [yearly, years, P]);

  const Tbl = ({ list }: { list: J[] }) => (
    <div className="scrollx">
      <table className="t">
        <thead><tr><th>모형</th><th>표본</th><th>MAE(원)</th><th>RMSE(원)</th><th>방향 적중</th><th>50% 포함</th><th>80% 포함</th><th>90% 포함</th><th>Brier(상승)</th><th>CRPS(%)</th><th>RW 대비 CRPS</th><th>DM p</th></tr></thead>
        <tbody>
          {list.map((r) => (
            <tr key={r.model} style={best && r.model === best.model ? { background: "var(--surface-2)", fontWeight: 700 } : undefined}>
              <td>{MODEL_SHORT[r.model]}{best && r.model === best.model ? " ★" : ""}</td><td className="num">{fmt(r.n)}</td>
              <td className="num">{fmt(r.mae, 1)}</td><td className="num">{fmt(r.rmse, 1)}</td>
              <td className="num">{r.hit == null ? "–" : (r.hit * 100).toFixed(1) + "%"}</td>
              <td className="num">{(r.cov50 * 100).toFixed(1)}%</td><td className="num">{(r.cov80 * 100).toFixed(1)}%</td><td className="num">{(r.cov90 * 100).toFixed(1)}%</td>
              <td className="num">{r.brier_up.toFixed(4)}</td><td className="num">{r.crps_pct.toFixed(4)}</td>
              <td className="num">{r.model === "A" ? "기준" : sgn(r.crps_vs_rw_pct, 2) + "%"}</td>
              <td className="num">{r.model === "A" ? "–" : r.dm_p < 0.001 ? "<0.001" : r.dm_p.toFixed(3)}</td>
            </tr>))}
        </tbody>
      </table>
    </div>
  );

  const gain = best && best.model !== "A" ? best.crps_vs_rw_pct : 0;
  return (
    <div className="space-y-4">
      <div className="card p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="mr-auto text-lg font-bold">모형별 정확도 (Walk-forward 백테스트)</h3>
          {[7, 30].map((h) => <button key={h} className="btn" aria-pressed={hz === h} onClick={() => setHz(h as 7 | 30)}>{h}일</button>)}
          <button className="btn" aria-pressed={period === "all"} onClick={() => setPeriod("all")}>{S.period[0].slice(0, 4)}~</button>
          <button className="btn" aria-pressed={period === "recent3y"} onClick={() => setPeriod("recent3y")}>최근 3년</button>
        </div>
        <div className="mt-3 rounded-lg p-3 text-[13px] leading-relaxed" style={{ background: "var(--surface-2)" }}>
          <b>{hz}일 전망 결과 요약.</b> CRPS 기준 최고 모형은 <b>{best && MODEL_SHORT[best.model]}</b>
          {best && best.model !== "A" ? <>이며 랜덤워크(장기 고정 변동성) 대비 {gain.toFixed(1)}% 낮은 확률오차를 보였습니다(DM p {best.dm_p < 0.001 ? "<0.001" : best.dm_p.toFixed(3)}). 개선은 <b>분포의 폭(변동성) 추정</b>에서 나왔고, 방향을 맞힌 것이 아닙니다.</> : <>입니다.</>}
          {" "}RMSE·MAE는 A~D가 모두 같습니다(중앙값=현재 환율). 방향 적중률은 방향 정보를 가진 조건부 모형에만 의미가 있으며, 아래 실험 모형에서도 50% 근처에 머무릅니다.
        </div>
        <p className="mt-3 text-sm font-semibold">공식 후보 모형 (A~D)</p>
        <Tbl list={official} />
        <p className="mt-4 text-sm font-semibold">실험적 조건부 모형 (릿지 평균 + EWMA 분산) — 공식 전망 미반영</p>
        <Tbl list={cond} />
        <ul className="mt-3 list-disc space-y-1 pl-5 text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
          <li>기간 {S.period[0]} ~ {S.period[1]} 기준일, 기준일마다 새로 추정(Walk-forward). 변동성·계수는 기준일까지 확정된 자료만 사용합니다. 겹치는 기간의 표본이라 유의성(DM p)은 Newey-West HAC로 보정했습니다.</li>
          <li>포함률은 명목 수준(50/80/90%)에 가까울수록 좋습니다. 80%·90% 구간이 명목보다 낮으면 구간이 너무 좁다는 뜻입니다.</li>
          <li>Brier는 '만기에 현재보다 높은가' 사건의 확률오차(0.25 = 동전던지기). 방향 정보가 없는 모형은 0.25 근처입니다.</li>
          <li>이 표는 <b>과거 자료로 재계산한 백테스트</b>입니다. 서비스 출시 이후의 실시간 전망 기록은 {S.live_count}건(7일·30일 합산)이며 아직 평가할 표본이 없습니다. 실시간 기록은 덮어쓰지 않고 추가만 합니다.</li>
        </ul>
      </div>
      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">연도별 평균 CRPS</h3>
        <EChart option={opt} height={260} />
      </div>
      <div className="card p-4 text-[13px] sm:p-5">
        <h3 className="text-lg font-bold">예측 데이터 내려받기</h3>
        <p className="mt-1" style={{ color: "var(--ink-2)" }}>기준일·목표일·중앙값·확률구간·상승확률·실제 환율·모형이 들어 있는 CSV입니다.</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <a className="btn" href="data/backtest_forecasts.csv" download>백테스트 전체 (CSV, 약 12MB)</a>
          {S.live_count > 0 ? <a className="btn" href="data/live_forecasts.csv" download>실시간 전망 기록 (CSV)</a> : <span className="btn">실시간 기록: 서비스 공개 후 시작</span>}
        </div>
        <p className="mt-2 text-[11px]" style={{ color: "var(--ink-3)" }}>데이터 기준일 {base}. 백테스트와 실시간 기록은 별도 파일로 구분합니다.</p>
      </div>
    </div>
  );
}
