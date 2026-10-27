import { useMemo, useState } from "react";
import EChart, { usePalette } from "./EChart";
import { J, fmt, pct, sgn, interp, MODEL_SHORT } from "../lib";

/** 상승/하락 확률 게이지: 왼쪽 파랑(하락·원화 강세) / 오른쪽 주황(상승·원화 약세). */
export function Gauge({ pUp }: { pUp: number }) {
  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full" style={{ background: "var(--surface-2)" }} aria-label={`상승 확률 ${pct(pUp)}`}>
        <div style={{ width: `${(1 - pUp) * 100}%`, background: "var(--down)" }} />
        <div style={{ width: `${pUp * 100}%`, background: "var(--up)" }} />
      </div>
      <div className="mt-1 flex justify-between text-xs num">
        <span style={{ color: "var(--down)" }}>하락 {pct(1 - pUp)} · 원화 강세</span>
        <span style={{ color: "var(--up)" }}>상승 {pct(pUp)} · 원화 약세</span>
      </div>
    </div>
  );
}

function IntervalRow({ label, lo, hi, spot, scale }: { label: string; lo: number; hi: number; spot: number; scale: [number, number] }) {
  const w = scale[1] - scale[0];
  const l = ((lo - scale[0]) / w) * 100, r = ((hi - scale[0]) / w) * 100, s = ((spot - scale[0]) / w) * 100;
  return (
    <div className="grid grid-cols-[48px_1fr_132px] items-center gap-2 text-xs">
      <span style={{ color: "var(--ink-3)" }}>{label}</span>
      <div className="relative h-2 rounded-full" style={{ background: "var(--surface-2)" }}>
        <div className="absolute top-0 h-2 rounded-full" style={{ left: `${l}%`, width: `${r - l}%`, background: "var(--ink-3)", opacity: 0.55 }} />
        <div className="absolute -top-0.5 h-3 w-px" style={{ left: `${s}%`, background: "var(--ink)" }} />
      </div>
      <span className="num text-right">{fmt(lo, 1)} ~ {fmt(hi, 1)}</span>
    </div>
  );
}

export function HorizonCard({ hz, spot, H }: { hz: number; spot: number; H: J }) {
  const m = H.models[H.selected];
  const scale: [number, number] = [H.models.A.pi90[0] - 4, H.models.A.pi90[1] + 4];
  return (
    <div className="card p-4 sm:p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-lg font-bold">{hz}일 후 전망</h3>
        <span className="text-xs" style={{ color: "var(--ink-3)" }}>{H.selected_name}</span>
      </div>
      <p className="mt-0.5 text-xs num" style={{ color: "var(--ink-3)" }}>
        기준일 {H.base_date} → 목표일 {H.target_date}{H.target_weekday ? `(${H.target_weekday}요일)` : ""} · {H.h_bd}영업일
      </p>
      <div className="mt-3">
        <div className="text-xs" style={{ color: "var(--ink-3)" }}>80% 확률로 이 범위 안</div>
        <div className="num font-extrabold" style={{ fontSize: "clamp(20px, 6.4vw, 30px)", whiteSpace: "nowrap" }}>{fmt(m.pi80[0], 0)} ~ {fmt(m.pi80[1], 0)}<span className="ml-1 text-base font-bold">원</span></div>
        <div className="mt-1.5 text-xs leading-relaxed" style={{ color: "var(--ink-3)" }}>현재 {fmt(spot, 1)}원 · 공식 모형은 방향 정보가 없어 중앙값이 현재 환율과 같습니다(검증된 방향 예측력 없음).</div>
      </div>
      <div className="mt-3"><Gauge pUp={m.p_up} /></div>
      <div className="mt-4 space-y-1.5">
        <IntervalRow label="50%" lo={m.pi50[0]} hi={m.pi50[1]} spot={spot} scale={scale} />
        <IntervalRow label="80%" lo={m.pi80[0]} hi={m.pi80[1]} spot={spot} scale={scale} />
        <IntervalRow label="90%" lo={m.pi90[0]} hi={m.pi90[1]} spot={spot} scale={scale} />
      </div>
      {(H.experimental_point.E0 || H.experimental_point.EP) && <p className="mt-3 rounded-lg p-2 text-[12px] leading-relaxed" style={{ background: "var(--surface-2)" }}>
        <b>실험적 점추정(공식 아님)</b>: 원·달러 단독 릿지 {H.experimental_point.E0 ? `${fmt(H.experimental_point.E0.value, 1)}원(${sgn(H.experimental_point.E0.mu_pct, 2)}%)` : "–"}{H.experimental_point.EP ? ` · +압력지수 ${fmt(H.experimental_point.EP.value, 1)}원(${sgn(H.experimental_point.EP.mu_pct, 2)}%)` : ""}. 백테스트에서 현재 환율보다 나은 방향·정확도가 확인되지 않았습니다.</p>}
      <p className="mt-3 text-[11px] leading-relaxed" style={{ color: "var(--ink-3)" }}>{H.evaluation_rule}. 막대의 세로선은 기준일 환율입니다.</p>
    </div>
  );
}

export function DistributionChart({ L }: { L: J }) {
  const [hz, setHz] = useState<7 | 30>(30);
  const H = L.horizons[String(hz)];
  const [model, setModel] = useState<string>("");
  const mk = model || H.selected;
  const P = usePalette();
  const dn = H.density[mk], card = H.models[mk];
  const option = useMemo(() => {
    const price: number[] = dn.price, pdf: number[] = dn.pdf;
    const data = price.map((p, i) => [p, pdf[i]]);
    const band = (lo: number, hi: number, a: number) => [{ xAxis: lo, itemStyle: { color: P.ink3, opacity: a } }, { xAxis: hi }];
    return {
      animation: false,
      grid: { left: 8, right: 12, top: 18, bottom: 28, containLabel: true },
      tooltip: { trigger: "axis", formatter: (ps: J) => {
        const x = ps[0].value[0]; const c = interp(price, dn.cdf, x);
        return `달러당 ${fmt(x, 1)}원<br/>${c == null ? "" : `이 값 이상일 확률 ${pct(1 - c)}`}`; } },
      xAxis: { type: "value", min: price[0], max: price[price.length - 1], axisLabel: { color: P.ink3, formatter: (v: number) => fmt(v, 0) }, axisLine: { lineStyle: { color: P.line } }, splitLine: { show: false } },
      yAxis: { type: "value", show: false },
      series: [{ type: "line", data, showSymbol: false, smooth: true, lineStyle: { width: 2, color: P.ink }, areaStyle: { color: P.ink3, opacity: 0.12 },
        markArea: { silent: true, data: [band(card.pi90[0], card.pi90[1], 0.08), band(card.pi80[0], card.pi80[1], 0.1), band(card.pi50[0], card.pi50[1], 0.14)] },
        markLine: { silent: true, symbol: "none", label: { color: P.ink2, fontSize: 11 }, data: [
          { xAxis: L.spot, name: "현재", lineStyle: { color: P.ink, type: "dashed" }, label: { formatter: `현재 ${fmt(L.spot, 1)}`, position: "insideEndTop" } },
          { xAxis: card.median, name: "중앙값", lineStyle: { color: P.up }, label: { formatter: `중앙값 ${fmt(card.median, 1)}`, position: "insideStartTop" } }] } }],
    };
  }, [dn, card, L.spot, P.ink, P.ink3, P.ink2, P.line, P.up]);

  const bins = useMemo(() => {
    const price: number[] = dn.price, cdf: number[] = dn.cdf;
    const step = hz === 7 ? 5 : 10;
    const lo = Math.floor(card.pi90[0] / step) * step - step, hi = Math.ceil(card.pi90[1] / step) * step + step;
    const rows: { a: number; b: number; p: number }[] = [];
    const F = (x: number) => (x <= price[0] ? 0 : x >= price[price.length - 1] ? 1 : (interp(price, cdf, x) as number));
    for (let a = lo; a < hi; a += step) rows.push({ a, b: a + step, p: F(a + step) - F(a) });
    return { rows, step };
  }, [dn, card, hz]);
  const maxP = Math.max(...bins.rows.map((r) => r.p));

  return (
    <div className="card p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="mr-auto text-lg font-bold">환율 확률분포</h3>
        {[7, 30].map((h) => <button key={h} className="btn" aria-pressed={hz === h} onClick={() => { setHz(h as 7 | 30); setModel(""); }}>{h}일 후</button>)}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {["A", "B", "C", "D", "P"].map((m) => (
          <button key={m} className="btn" aria-pressed={mk === m} onClick={() => setModel(m)}>{MODEL_SHORT[m]}{m === H.selected ? " ★공식" : ""}</button>
        ))}
      </div>
      <EChart option={option} height={300} />
      <p className="text-[11px]" style={{ color: "var(--ink-3)" }}>
        짙은 음영부터 50%·80%·90% 예측구간. 곡선 위에 마우스·손가락을 올리면 해당 환율 이상일 확률이 표시됩니다. 달러당 원화값 기준.
      </p>
      <div className="scrollx mt-4">
        <table className="t">
          <thead><tr><th>환율 구간(원)</th><th>확률</th><th style={{ width: "50%" }}></th></tr></thead>
          <tbody>
            {bins.rows.filter((r) => r.p >= 0.002).map((r) => (
              <tr key={r.a} style={r.a <= L.spot && L.spot < r.b ? { background: "var(--surface-2)" } : undefined}>
                <td className="num">{fmt(r.a)} ~ {fmt(r.b)}{r.a <= L.spot && L.spot < r.b ? "  ← 현재" : ""}</td>
                <td className="num">{pct(r.p)}</td>
                <td><div className="h-2 rounded-full" style={{ width: `${(r.p / maxP) * 100}%`, background: r.a >= L.spot ? "var(--up)" : "var(--down)", opacity: 0.8 }} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ThresholdCalculator({ L }: { L: J }) {
  const [txt, setTxt] = useState("1400");
  const K = Number(txt.replace(/,/g, ""));
  const valid = isFinite(K) && K > 0;
  const rows = ["7", "30"].map((h) => {
    const H = L.horizons[h]; const dn = H.density[H.selected]; const b = H.barrier[H.selected];
    const k = Math.log(K / L.spot);
    const c = interp(dn.price, dn.cdf, K);
    const endGE = K <= dn.price[0] ? 1 : K >= dn.price[dn.price.length - 1] ? 0 : 1 - (c as number);
    // 격자는 k=0 이 빠져 있다(양쪽 격자를 따로 보간).
    const side = k >= 0 ? b.k.map((x: number, i: number) => [x, i]).filter((a: number[]) => a[0] > 0) : b.k.map((x: number, i: number) => [x, i]).filter((a: number[]) => a[0] < 0);
    // k=0(현재가)에서는 이미 닿아 있으므로 확률 1 로 보간 끝점을 둔다
    const xs0 = side.map((a: number[]) => a[0]), idx = side.map((a: number[]) => a[1]);
    const xs = k >= 0 ? [0, ...xs0] : [...xs0, 0];
    const get = (arr: number[]) => {
      const v = idx.map((i: number) => arr[i]);
      return interp(xs, k >= 0 ? [1, ...v] : [...v, 1], k);
    };
    const bridge = get(b.touch_bridge), disc = get(b.touch_discrete);
    return { h, H, endGE, bridge, disc, dir: k >= 0 ? "이상" : "이하", k };
  });
  return (
    <div className="card p-4 sm:p-5">
      <h3 className="text-lg font-bold">특정 환율 도달 확률 계산기</h3>
      <div className="mt-3 flex items-center gap-2">
        <input inputMode="numeric" value={txt} onChange={(e) => setTxt(e.target.value)} aria-label="환율(달러당 원)"
          className="num w-32 rounded-lg border px-3 py-2 text-lg font-bold" style={{ background: "var(--surface)", borderColor: "var(--line)", color: "var(--ink)" }} />
        <span className="text-sm" style={{ color: "var(--ink-2)" }}>원 (현재 {fmt(L.spot, 1)}원)</span>
      </div>
      {!valid ? <p className="mt-3 text-sm">숫자를 입력하세요.</p> : (
        <div className="scrollx mt-4">
          <table className="t">
            <thead><tr><th>기간</th><th>만기 시점에 {K >= L.spot ? "이상" : "이하"}일 확률</th><th>기간 중 한 번이라도 {K >= L.spot ? "돌파" : "하회"} (보정)</th><th>같은 확률 (이산 시뮬레이션)</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.h}>
                  <td>{r.h}일 ({r.H.target_date})</td>
                  <td className="num font-bold">{pct(K >= L.spot ? r.endGE : 1 - r.endGE)}</td>
                  <td className="num font-bold">{r.bridge == null ? "격자(±10%) 밖" : pct(r.bridge)}</td>
                  <td className="num">{r.disc == null ? "–" : pct(r.disc)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <details className="mt-3"><summary className="cursor-pointer text-[12px] font-semibold" style={{ color: "var(--ink-2)" }}>만기 확률과 기간 중 돌파 확률의 차이 · 한계 (펼치기)</summary>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
        <li><b>만기 시점 확률</b>은 목표일 한 날의 환율이 기준을 넘을 확률이고, <b>기간 중 돌파 확률</b>은 기간 안에 한 번이라도 넘을 확률이라 항상 더 큽니다.</li>
        <li>일별 종가만 시뮬레이션하면 거래일 사이의 돌파를 놓쳐 확률이 낮게 나옵니다(이산 시뮬레이션 열). 브라운 다리 보정으로 이를 근사한 값을 기본으로 표시합니다. 일중 고점(장중가) 돌파와는 다릅니다.</li>
        <li>사용 모형: 7일 {L.horizons["7"].selected_name}, 30일 {L.horizons["30"].selected_name}. 정규분포 꼬리는 극단 사건을 과소평가할 수 있습니다.</li>
      </ul>
      </details>
    </div>
  );
}

export function ModelTable({ L }: { L: J }) {
  const [hz, setHz] = useState<"7" | "30">("30");
  const H = L.horizons[hz];
  return (
    <div className="card p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <h3 className="mr-auto text-lg font-bold">모형별 비교</h3>
        {(["7", "30"] as const).map((h) => <button key={h} className="btn" aria-pressed={hz === h} onClick={() => setHz(h)}>{h}일</button>)}
      </div>
      <div className="scrollx mt-2">
        <table className="t">
          <thead><tr><th>모형</th><th>중앙값</th><th>상승확률</th><th>80% 구간</th><th>90% 구간</th></tr></thead>
          <tbody>
            {(["A", "B", "C", "D", "P", "PR"] as const).filter((m) => H.models[m]).map((m) => {
              const c = H.models[m];
              return (<tr key={m} style={m === H.selected ? { background: "var(--surface-2)", fontWeight: 700 } : undefined}>
                <td>{MODEL_SHORT[m]}{m === H.selected ? " ★" : ""}</td><td className="num">{fmt(c.median, 1)}</td><td className="num">{pct(c.p_up)}</td>
                <td className="num">{fmt(c.pi80[0], 0)}~{fmt(c.pi80[1], 0)}</td><td className="num">{fmt(c.pi90[0], 0)}~{fmt(c.pi90[1], 0)}</td></tr>);
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
        ★는 지금까지 실현이 확정된 예측의 평균 CRPS가 가장 낮은 모형입니다. 네 모형은 모두 방향성(drift)을 가정하지 않으므로 상승확률이 50% 근처이며, 방향 예측력은 검증되지 않았습니다.
      </p>
      <details className="mt-3 rounded-lg border p-3 text-[13px]" style={{ borderColor: "var(--line)" }}>
        <summary className="cursor-pointer font-semibold">모형 설명 보기</summary>
        <div className="mt-2 space-y-2 leading-relaxed" style={{ color: "var(--ink-2)" }}>
          <p><b>공통 원리.</b> 환율의 일별 변화율(로그수익률)을 만기까지 더한 값의 분포를 만들고, 방향(drift)은 0으로 둡니다. 그래서 모든 모형의 중앙값이 현재 환율이고, 모형끼리 다른 것은 <b>얼마나 넓게 흔들리느냐(변동성)</b>입니다. 만기까지의 영업일 수(7일→5일, 30일→21~22일)의 제곱근에 비례해 폭이 커집니다.</p>
          <p><b>A 랜덤워크(장기 변동성).</b> 내일 환율은 오늘 환율에서 무작위로 움직인다는 기준 모형입니다. 변동성은 2000년 이후 전체 기간의 값을 씁니다. 위기 때의 큰 변동까지 평균에 섞여 평소에는 구간이 넓게 나오는 경향이 있습니다(포함률이 명목보다 높음).</p>
          <p><b>B 역사적 변동성.</b> 최근 252영업일(약 1년)의 변동성만 사용합니다. 최근 분위기를 반영하지만 변화에 천천히 반응합니다.</p>
          <p><b>C EWMA.</b> 최근 변동에 더 큰 가중치를 주는 지수가중 변동성(λ=0.94)입니다. 변동성이 커지면 구간이 빠르게 넓어지고 잠잠해지면 빠르게 좁아집니다. 백테스트에서 대체로 가장 정확했습니다.</p>
          <p><b>D 역사적 재표본추출(FHS).</b> 최근 약 6년의 실제 수익률을 EWMA 변동성으로 표준화한 뒤 무작위로 뽑아 합산합니다. 정규분포를 가정하지 않아 급등락 같은 두꺼운 꼬리를 더 잘 반영하고, 분포가 약간 비대칭이어서 상승확률이 50%에서 조금 벗어납니다.</p>
          <p><b>★ 공식 모형을 고르는 법.</b> 가장 복잡한 모형이 아니라, 그 날짜까지 실현이 확정된 과거 예측의 평균 점수(CRPS, 낮을수록 좋음)가 가장 낮은 모형입니다. 과거 날짜를 재현할 때도 그 시점까지의 성적만 써서 미래 정보가 섞이지 않습니다.</p>
          <p><b>한계.</b> 방향을 맞히는 모형이 아닙니다. 상승확률이 50% 근처인 것은 "모른다"는 뜻입니다. 금리·엔화·뉴스 등을 넣은 조건부 모형은 성적표에 실험으로 따로 두었고, 백테스트에서 개선이 확인되지 않았습니다.</p>
        </div>
      </details>
    </div>
  );
}
