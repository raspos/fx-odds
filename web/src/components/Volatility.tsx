import { useMemo } from "react";
import EChart, { usePalette } from "./EChart";
import { J, fmt, sgn } from "../lib";

const Src = ({ V }: { V: J }) => (
  <p className="mt-1 text-[11px]" style={{ color: "var(--ink-3)" }}>출처: {V.source} · 관측 기준일 <span className="num">{V.asof}</span> (이용 가능일 {V.available_at}) · 세로 점선은 관측 범위·거래시간 변경일</p>
);

function Tile({ k, v, s, color }: { k: string; v: string; s?: string; color?: string }) {
  return (<div className="tile"><div className="k">{k}</div><div className="v" style={color ? { color } : undefined}>{v}</div>{s && <div className="s">{s}</div>}</div>);
}

export default function Volatility({ V }: { V: J }) {
  const P = usePalette();
  const L = V.latest;

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
  const o4 = useMemo(() => ({ ...base, xAxis: xAxis(V.fxvi_3y.dates), yAxis: yAxis("FXVI", { min: 0, max: 100, scale: false }),
    series: [{ name: "참고용(관측 범위 변경 무시)", type: "line", showSymbol: false, connectNulls: false, data: V.fxvi_3y.ref, lineStyle: { color: P.down || "#2a78d6", width: 2.2, type: [6, 4] }, itemStyle: { color: P.down || "#2a78d6" } },
      { name: "FXVI", type: "line", showSymbol: false, connectNulls: false, data: V.fxvi_3y.fxvi, lineStyle: { color: P.ink, width: 1.6 }, areaStyle: { color: P.ink3, opacity: 0.1 },
      markLine: { silent: true, symbol: "none", data: [...brk(V.fxvi_3y.dates), { yAxis: 50, lineStyle: { color: P.line, type: "dotted" }, label: { show: false } }] } }] }), [V, P]);
  const o5 = useMemo(() => ({ ...base, xAxis: xAxis(V.level_vs_vol.dates), yAxis: [yAxis("원/달러(매매기준율)"), yAxis("20일 파킨슨 변동성(연율 %)", { splitLine: { show: false } })],
    series: [{ name: "환율(왼쪽)", type: "line", showSymbol: false, data: V.level_vs_vol.fix, lineStyle: { color: P.ink, width: 1.5 }, markLine: { silent: true, symbol: "none", data: brk(V.level_vs_vol.dates) } },
      { name: "변동성(오른쪽)", type: "line", yAxisIndex: 1, showSymbol: false, data: V.level_vs_vol.park20_ann, lineStyle: { color: P.up, width: 1.5 } }] }), [V, P]);
  const yrs = V.yearly.filter((y: J) => y.n > 60);
  const o6 = useMemo(() => ({ ...base, legend: undefined, xAxis: xAxis(yrs.map((y: J) => String(y.year))), yAxis: yAxis("평균 일중 변동폭(원)", { scale: false }),
    tooltip: { trigger: "axis", formatter: (p: J) => { const y = yrs[p[0].dataIndex]; return `${y.year}년 · ${y.n}세션<br/>평균 변동폭 ${y.mean_range_won}원 · 중앙 변동률 ${y.median_range_pct}%${y.year === 2024 ? "<br/>(7월 마감 연장 전후 혼합)" : y.year > 2024 ? "<br/>(연장된 관측 범위)" : ""}`; } },
    series: [{ type: "bar", data: yrs.map((y: J) => ({ value: y.mean_range_won, itemStyle: { color: y.year < 2024 ? P.ink3 : y.year === 2024 ? P.down : P.up, opacity: 0.85 } })) }] }), [V, P]);

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
        <details className="mt-3 rounded-lg border p-3" style={{ borderColor: "var(--line)" }}>
          <summary className="cursor-pointer text-[13px] font-bold">FXVI가 무엇인가요? 자세한 설명 (펼치기)</summary>
          <div className="mt-2 space-y-3 text-[13px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
            <div><b>한 줄 요약</b><br />FXVI는 "요즘 원/달러가 평소보다 얼마나 크게 출렁이고 있나"를 <b>0~100점</b>으로 보여 주는 지수입니다. 점수가 높을수록 최근 흔들림이 과거 1년 중 큰 편이고, 낮을수록 잠잠한 편입니다. 지금은 <b className="num">{L.fxvi == null ? "산출 보류" : `${fmt(L.fxvi, 0)}점`}</b>{L.fxvi != null && <>으로, 최근 1년 중 약 <b className="num">{fmt(100 - L.fxvi, 0)}%</b>의 시기가 지금보다 더 크게 흔들렸다는 뜻입니다.</>}</div>
            <div><b>어떻게 만드나요 (4단계)</b>
              <ol className="mt-1 list-decimal space-y-1 pl-5">
                <li><b>하루의 흔들림 재기</b> — 그날 가장 높았던 값(고가)과 가장 낮았던 값(저가)의 차이를 봅니다. 종가만 보면 "하루 종일 크게 오르내렸다가 제자리로 돌아온 날"이 잠잠한 날로 보이는 문제가 있어, 고가·저가를 씁니다.</li>
                <li><b>숫자 하나로 바꾸기(파킨슨 변동성)</b> — 고가/저가 비율을 로그로 바꿔 제곱하고 4·ln2로 나눕니다(파킨슨 공식). 날마다의 흔들림 크기를 통계적으로 비교할 수 있는 숫자로 만드는 과정입니다.</li>
                <li><b>최근 20일 평균내기</b> — 하루 값은 들쭉날쭉하므로 최근 20거래일(약 한 달)을 평균냅니다. 지금 값은 하루 약 <span className="num">{fmt(L.park20_daily_pct, 2)}%</span> 수준이고, 1년으로 환산(×√252)하면 약 <span className="num">{fmt(L.park20_ann_pct, 1)}%</span>입니다.</li>
                <li><b>과거와 순위 매기기</b> — 이 값을 지난 252거래일(약 1년)의 같은 값들과 비교해 "몇 %의 날보다 더 컸는가"를 0~100으로 매깁니다. 이게 FXVI입니다. 50이면 1년 중 딱 중간, 90이면 1년 중 가장 크게 흔들리는 10% 안에 든다는 뜻입니다.</li>
              </ol></div>
            <div><b>점수는 이렇게 읽으세요</b>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                <li><b>0~25 (잠잠함)</b>: 최근 한 달이 지난 1년 중 가장 조용한 편입니다. 값이 낮다고 앞으로도 조용하다는 보장은 없습니다.</li>
                <li><b>25~75 (보통)</b>: 평소 수준의 흔들림입니다.</li>
                <li><b>75~100 (크게 흔들림)</b>: 최근 한 달이 지난 1년 중 가장 크게 흔들린 편입니다. 보통 위기·큰 이벤트·급등락 직후에 나타납니다.</li>
                <li>"전일 대비 FXVI"는 순위가 하루 사이 얼마나 움직였는지입니다. 20일 평균이라 하루에 크게 바뀌지 않는 것이 정상입니다.</li>
              </ul></div>
            <div><b>이 지수가 아닌 것</b>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                <li><b>방향을 말하지 않습니다.</b> 점수가 높다고 환율이 오른다(원화 약세)는 뜻이 아니고, 낮다고 내린다는 뜻도 아닙니다. 오르내림의 <b>크기</b>만 봅니다.</li>
                <li><b>미래를 예측하지 않습니다.</b> 이미 지나간 한 달의 실제 움직임(실현 변동성)을 보여 줍니다. 시장이 앞으로 크게 움직일 것으로 기대하는 정도를 보여 주는 옵션 기반 지수(VIX 같은 내재변동성)와는 다릅니다.</li>
                <li><b>압력 지수(FPI)·뉴스 압력과 다릅니다.</b> 그쪽은 어느 방향으로 미는 힘인지를, FXVI는 흔들림의 정도를 말하므로 합산하지 않습니다.</li>
              </ul></div>
            <div><b>왜 어떤 기간은 점수가 비어 있나요 (그래프 ④)</b><br />2024년 7월 1일에 외환시장 마감이 새벽 2시로 늘면서, 하루 고가·저가가 재는 범위가 넓어졌습니다(같은 날도 고가-저가 차이가 커짐). 재는 방식이 다른 값을 한 순위에 섞으면 변동성이 실제와 상관없이 높아 보이므로, FXVI는 <b>같은 방식으로 잰 과거 252거래일끼리만</b> 비교합니다. 그래서 2024-07 ~ 2025-07은 비교할 새 방식의 과거가 아직 부족해 실선을 그리지 않고, 대신 참고용 점선만 표시합니다. 점선은 재는 방식 변경을 무시한 값이라 평균 {(() => { const r = V.fxvi_3y.ref.filter((x: number | null) => x != null) as number[]; return r.length ? fmt(r.reduce((a, b) => a + b, 0) / r.length, 0) : "–"; })()}점으로, 중간(50)보다 훨씬 높게 쏠려 있습니다. 변동성이 실제로 높아서가 아니라 새 방식의 값이 예전 값보다 크기 때문에 생기는 쏠림입니다. 원자료는 이 기간에도 모두 있습니다.</div>
            <div><b>알아 두면 좋은 점</b>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                <li><b>한 달치 평균이라 늦게 반응</b>합니다. 큰 사건 직후에는 오르는 데 며칠 걸리고, 사건이 지나도 20일 동안은 점수가 남아 있습니다.</li>
                <li><b>비교 대상은 "최근 1년"입니다.</b> 큰 위기가 오래 이어지면 위기 자체가 새 기준이 되어 점수가 내려갈 수 있습니다.</li>
                <li>고가·저가는 한국은행이 집계한 은행간 시장 기준이며, 해외시장·NDF의 새벽 가격은 포함하지 않습니다. 2026-07-06부터 24시간 거래가 시작됐지만 변동폭 수준에는 통계적으로 뚜렷한 변화가 확인되지 않아 같은 구간으로 처리했습니다.</li>
              </ul></div>
          </div>
        </details>
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
        <p className="text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
          <b>실선</b>은 같은 방식으로 잰 과거 252거래일과만 비교한 FXVI입니다. 2024년 7월에 외환시장 마감이 새벽 2시로 늘면서 하루 고가·저가의 재는 범위가 넓어졌고, 새 방식의 과거가 252일 쌓이기 전에는 실선을 그리지 않습니다(원자료는 모두 있습니다).
          <b> 파란 점선</b>은 그 빈 구간에 재는 방식의 변경을 무시하고 전체 과거와 비교한 <b>참고용</b> 값입니다. 새 방식의 값이 예전 값보다 크게 나오는 효과가 섞여 있어 <b>실제보다 높게 나올 수 있으니</b> 실선과 같은 기준으로 읽지 마세요.</p><Src V={V} /></div>
      <div className="card p-4 sm:p-5"><h3>⑤ 환율 수준과 변동성</h3><EChart option={o5} height={260} /><Src V={V} /></div>
      <div className="card p-4 sm:p-5"><h3>⑥ 연도별 평균 일중 변동폭</h3><EChart option={o6} height={240} />
        <p className="text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>회색: 2023년까지(09:00~15:30 중심 관측), 파랑: 2024년(7월 마감 연장 전후 혼합), 주황: 2025년 이후(연장된 관측 범위). 2024-07 이후의 큰 값은 변동성 증가와 관측 범위 확대가 섞여 있어 직접 비교할 수 없습니다.</p><Src V={V} /></div>

    </div>
  );
}
