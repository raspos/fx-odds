import { useEffect, useMemo, useState } from "react";
import { J, fmt, pct, sgn } from "./lib";
import EChart, { usePalette } from "./components/EChart";
import { DistributionChart, HorizonCard, ModelTable, ThresholdCalculator, Gauge } from "./components/Forecast";
import Radar from "./components/Radar";
import Scorecard from "./components/Scorecard";
import Methodology from "./components/Methodology";
import { Pressure } from "./components/Pressure";
import { Events } from "./components/Events";
import { News } from "./components/News";

const FILES = ["latest", "series", "scorecard", "radar", "history", "meta", "fpi", "events", "news"] as const;

function Section({ id, no, title, sub, children }: { id: string; no: string; title: string; sub: string; children: React.ReactNode }) {
  return (
    <section id={id} className="mt-6">
      <div className="mb-3">
        <div className="text-xs font-bold tracking-widest" style={{ color: "var(--ink-3)" }}>SECTION {no}</div>
        <h2 className="text-2xl font-extrabold">{title}</h2>
        <p className="text-sm" style={{ color: "var(--ink-2)" }}>{sub}</p>
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function Pending({ title, items, why }: { title: string; items: string[]; why: string }) {
  return (
    <div className="card border-dashed p-4 sm:p-5">
      <div className="flex items-center gap-2"><span className="rounded-full px-2 py-0.5 text-xs font-bold" style={{ background: "var(--warn-bg)", color: "var(--warn-ink)" }}>준비 중</span><h3 className="text-lg font-bold">{title}</h3></div>
      <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--ink-2)" }}>{why}</p>
      <ul className="mt-2 list-disc pl-5 text-[13px] leading-relaxed" style={{ color: "var(--ink-3)" }}>{items.map((s) => <li key={s}>{s}</li>)}</ul>
      <p className="mt-2 text-xs" style={{ color: "var(--ink-3)" }}>가짜 수치로 채우지 않습니다. 지표 수집기와 백테스트가 완성되면 이 자리에 공개합니다.</p>
    </div>
  );
}

function SpotChart({ S, spot }: { S: J; spot: number }) {
  const P = usePalette();
  const opt = useMemo(() => ({
    animation: false, grid: { left: 4, right: 4, top: 6, bottom: 4, containLabel: false }, tooltip: { trigger: "axis", valueFormatter: (v: number) => fmt(v, 1) + "원" },
    xAxis: { type: "category", data: S.dates, show: false }, yAxis: { type: "value", show: false, min: "dataMin", max: "dataMax" },
    series: [{ type: "line", data: S.usdkrw, showSymbol: false, lineStyle: { width: 1.5, color: P.ink }, areaStyle: { color: P.ink3, opacity: 0.1 } }],
  }), [S, P]);
  return <EChart option={opt} height={70} />;
}

export default function App() {
  const [D, setD] = useState<Record<string, J> | null>(null);
  const [err, setErr] = useState("");
  const [asOf, setAsOf] = useState<string | null>(null);
  const [tab, setTab] = useState<string>(() => (location.hash.slice(1) || "s1"));
  useEffect(() => { location.hash = tab; }, [tab]);

  useEffect(() => {
    Promise.all(FILES.map((f) => fetch(`data/${f}.json`).then((r) => { if (!r.ok) throw new Error(f); return r.json(); })))
      .then((arr) => setD(Object.fromEntries(FILES.map((f, i) => [f, arr[i]]))))
      .catch((e) => setErr(`데이터를 불러오지 못했습니다: ${e.message}`));
  }, []);

  const hist: J[] = D?.history.origins ?? [];
  const entry = useMemo(() => {
    if (!asOf) return null;
    let lo: J = null; for (const o of hist) { if (o.d <= asOf) lo = o; else break; } return lo;
  }, [asOf, hist]);
  const histMode = !!asOf && !!entry && entry.d !== D?.latest.base_date;

  if (err) return <div className="p-8">{err}</div>;
  if (!D) return <div className="p-8" style={{ color: "var(--ink-3)" }}>불러오는 중…</div>;
  const L = D.latest, M = D.meta;
  const first = hist[0]?.d, last = L.base_date;
  const up = L.change >= 0;

  return (
    <div className="mx-auto max-w-5xl px-4 pb-24 sm:px-6">
      <div className="-mx-4 flex items-center gap-1 border-b px-4 py-1.5 text-[12px] sm:-mx-6 sm:px-6" style={{ borderColor: "var(--line)", background: "var(--surface-2)" }} aria-label="서비스 전환">
        <span style={{ color: "var(--ink-3)" }}>서비스</span>
        <a href="https://bokwatch.pages.dev/" className="rounded-full px-2.5 py-0.5" style={{ color: "var(--ink-2)" }}>BOK워치 · 금통위 금리 결정 ↗</a>
        <span className="rounded-full px-2.5 py-0.5 font-bold" style={{ background: "var(--ink)", color: "var(--bg)" }} aria-current="page">FX ODDS · 환율</span>
      </div>
      <header className="sticky top-0 z-10 -mx-4 border-b px-4 py-3 sm:-mx-6 sm:px-6" style={{ background: "color-mix(in srgb, var(--bg) 92%, transparent)", borderColor: "var(--line)", backdropFilter: "blur(8px)" }}>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="mr-auto">
            <h1 className="text-xl font-black tracking-tight">FX ODDS</h1>
            <p className="text-xs" style={{ color: "var(--ink-2)" }}>환율의 확률과 압력을 읽다</p>
          </div>
          <label className="flex items-center gap-2 text-xs" style={{ color: "var(--ink-2)" }}>
            기준일
            <input type="date" min={first} max={last} value={asOf ?? last} onChange={(e) => setAsOf(e.target.value && e.target.value < last ? e.target.value : null)}
              className="num rounded-lg border px-2 py-1 text-sm" style={{ background: "var(--surface)", borderColor: "var(--line)", color: "var(--ink)" }} />
          </label>
          {asOf && <button className="btn" onClick={() => setAsOf(null)}>최신으로</button>}
        </div>
        <nav className="mt-2 flex gap-1.5 overflow-x-auto text-[13px]" role="tablist">
          {[["s1", "환율의 미래"], ["s2", "압력·뉴스"], ["s3", "동조화 레이더"], ["s5", "예측 성적표"], ["s6", "방법론"]].map(([id, t]) => (
            <button key={id} role="tab" aria-selected={tab === id} className="btn whitespace-nowrap" aria-pressed={tab === id} onClick={() => { setTab(id); window.scrollTo(0, 0); }}>{t}</button>))}
        </nav>
      </header>

      <div className="card mt-4 grid grid-cols-3 gap-3 p-3 text-center sm:p-4">
        <div><div className="text-[11px]" style={{ color: "var(--ink-3)" }}>{histMode ? entry.d : L.base_date} 원/달러</div><div className="num text-xl font-black">{fmt(histMode ? entry.spot : L.spot, 1)}</div></div>
        {(["7", "30"] as const).map((h) => {
          const e = histMode ? entry["h" + h] : null; const H = L.horizons[h]; const m = H.models[H.selected];
          const med = e ? e.q[3] : m.median, pu = e ? e.pu : m.p_up;
          return (<div key={h}><div className="text-[11px]" style={{ color: "var(--ink-3)" }}>{h}일 후 80% 범위</div><div className="num text-lg font-black">{fmt(e ? e.q[1] : m.pi80[0], 0)}~{fmt(e ? e.q[5] : m.pi80[1], 0)}</div></div>);
        })}
      </div>
      {M.stale_warning && <div className="mt-4 rounded-lg p-3 text-sm" style={{ background: "var(--warn-bg)", color: "var(--warn-ink)", border: "1px solid var(--warn-line)" }}>
        ⚠ 자료가 {M.stale_days}일 전 기준입니다. 최근 수집이 실패했을 수 있어 이전 정상 데이터를 표시합니다.</div>}
      {M.sources.filter((x: J) => x.stale).map((x: J) => <div key={x.series} className="mt-3 rounded-lg p-3 text-sm" style={{ background: "var(--warn-bg)", color: "var(--warn-ink)", border: "1px solid var(--warn-line)" }}>
        ⚠ {x.name} 자료가 {x.age_days}일 전({x.last_obs}) 기준입니다(허용 {x.threshold_days}일 초과). 이전 정상 데이터를 표시합니다.</div>)}
      {M.failed_series.length > 0 && <div className="mt-3 rounded-lg p-3 text-sm" style={{ background: "var(--warn-bg)", color: "var(--warn-ink)" }}>최근 수집 실패: {M.failed_series.join(", ")}</div>}
      {histMode && <div className="mt-4 rounded-lg p-3 text-sm" style={{ background: "var(--warn-bg)", color: "var(--warn-ink)", border: "1px solid var(--warn-line)" }}>
        <b>과거 자료 재계산 · {entry.d}.</b> 기준일까지의 환율만으로 다시 계산한 값이며, 당시 실제로 공개된 전망이 아닙니다. 당시 보존된 뉴스·보고서·압력 지수는 아직 없어 표시하지 않습니다.</div>}

      {tab === "s1" && <Section id="s1" no="01" title="환율의 미래" sub="7일·30일 뒤 달러당 원화값의 확률분포">
        <div className="card p-4 sm:p-5">
          <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
            <div>
              <div className="text-xs" style={{ color: "var(--ink-3)" }}>{histMode ? `${entry.d} 원·달러 환율 (달러당 원화값)` : "최신 원·달러 환율 (달러당 원화값)"}</div>
              <div className="num text-4xl font-black">{fmt(histMode ? entry.spot : L.spot, 1)}<span className="ml-1 text-lg font-bold">원</span></div>
            </div>
            {!histMode && <div className="num pb-1 text-lg font-bold" style={{ color: up ? "var(--up)" : "var(--down)" }}>
              {up ? "▲" : "▼"} {sgn(L.change, 1)}원 ({sgn(L.change_pct, 2)}%) <span className="text-xs font-normal" style={{ color: "var(--ink-3)" }}>전 거래일 {L.prev_date} 대비</span></div>}
          </div>
          <div className="mt-2 text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
            관측일 <b className="num">{histMode ? entry.d : L.base_date}</b> · 한국은행 ECOS · {L.definition}. 상승은 달러당 원화값 상승(원화 약세), 하락은 원화 강세입니다.
          </div>
          {!histMode && <SpotChart S={D.series} spot={L.spot} />}
        </div>

        {histMode ? (
          <div className="grid gap-4 md:grid-cols-2">
            {(["h7", "h30"] as const).map((k) => {
              const e = entry[k]; const hz = k === "h7" ? 7 : 30;
              if (!e) return <div key={k} className="card p-4">{hz}일 전망 자료 없음</div>;
              return (
                <div key={k} className="card p-4 sm:p-5">
                  <h3 className="text-lg font-bold">{hz}일 후 전망 <span className="text-xs font-normal" style={{ color: "var(--ink-3)" }}>(모형 {e.m} · 과거 자료 재계산)</span></h3>
                  <div className="num mt-2 text-3xl font-extrabold">{fmt(e.q[3], 1)}</div>
                  <div className="mt-3"><Gauge pUp={e.pu} /></div>
                  <table className="t mt-3"><tbody>
                    <tr><td>50% 구간</td><td className="num">{fmt(e.q[2], 1)} ~ {fmt(e.q[4], 1)}</td></tr>
                    <tr><td>80% 구간</td><td className="num">{fmt(e.q[1], 1)} ~ {fmt(e.q[5], 1)}</td></tr>
                    <tr><td>90% 구간</td><td className="num">{fmt(e.q[0], 1)} ~ {fmt(e.q[6], 1)}</td></tr>
                    <tr><td>이후 실현 환율</td><td className="num font-bold">{e.real == null ? "아직 목표일 전" : `${fmt(e.real, 1)} (${e.td})`}</td></tr>
                    {e.real != null && <tr><td>실현값의 위치</td><td className="num">{e.real >= e.q[0] && e.real <= e.q[6] ? (e.real >= e.q[1] && e.real <= e.q[5] ? (e.real >= e.q[2] && e.real <= e.q[4] ? "50% 구간 안" : "80% 구간 안") : "90% 구간 안") : "90% 구간 밖"}</td></tr>}
                  </tbody></table>
                </div>);
            })}
          </div>
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-2">
              <HorizonCard hz={7} spot={L.spot} H={L.horizons["7"]} />
              <HorizonCard hz={30} spot={L.spot} H={L.horizons["30"]} />
            </div>
            <DistributionChart L={L} />
            <ModelTable L={L} />
            <ThresholdCalculator L={L} />
          </>
        )}
        <p className="text-[12px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
          통계적 환율 전망(A)입니다. 환율 수익률과 변동성만으로 계산했고 방향에 대한 판단은 담지 않았습니다. 정성 압력(B)·통합 전망(C)은 검증 전이라 반영하지 않습니다.
        </p>
      </Section>}

      {tab === "s2" && <Section id="s2" no="02" title="압력·뉴스" sub="뉴스가 환율을 미는 방향(실험) · 통계 압력 지수(FPI) · 시장 사건">
        <News N={D.news} refDate={L.base_date} asOf={histMode ? entry.d : null} />
        <h3 className="pt-2 text-xl font-extrabold">통계로 본 압력 (FPI)</h3>
        <Pressure P={D.fpi} asOf={histMode ? entry.d : null} S={D.series} />
        <h3 className="pt-2 text-xl font-extrabold">시장 사건 (통계 추출)</h3>
        <Events E={D.events} asOf={histMode ? entry.d : null} refDate={histMode ? entry.d : L.base_date} />
      </Section>}

      {tab === "s3" && <Section id="s3" no="03" title="원화 동조화 레이더" sub="원화는 최근 엔화·위안화·대만 달러 중 어느 통화와 가장 밀접하게 움직였나">
        <Radar R={D.radar} asOf={histMode ? entry.d : null} />
      </Section>}

      

      {tab === "s5" && <Section id="s5" no="04" title="예측 성적표" sub="FX SCORECARD — 이 서비스의 전망은 랜덤워크보다 실제로 정확한가">
        <Scorecard S={D.scorecard} base={L.base_date} />
      </Section>}

      {tab === "s6" && <Section id="s6" no="05" title="방법론" sub="원시자료 · 계산식 · 한계 · 변경 이력">
        <Methodology meta={M} />
      </Section>}

      <footer className="mt-12 border-t pt-4 text-[12px] leading-relaxed" style={{ borderColor: "var(--line)", color: "var(--ink-3)" }}>
        최종 갱신 {M.updated_at.replace("T", " ").slice(0, 16)} KST · 원·달러 기준 {L.base_date}(ECOS) · Yahoo {M.latest_obs["yahoo:USDKRW"]} · {M.version}<br />
        <p className="mt-2">면책: 이 사이트의 확률·전망은 공개 금리와 언론 보도를 바탕으로 한 모형 추정치이며, 투자 자문이나 특정 금융상품의 매수·매도 권유가 아닙니다. 수치의 정확성·완전성·적시성을 보장하지 않습니다. 기관 전망과 발언은 보도 인용이라 원문과 다를 수 있습니다. 이 정보를 이용하거나 해석해 내린 판단과 그 결과의 책임은 전적으로 이용자에게 있으며, 운영자는 이로 인해 생긴 손해에 책임지지 않습니다.</p>
        <p className="mt-2">© 2026 databrew · 이 사이트에는 추후 광고가 게재될 수 있습니다.</p>
      </footer>
    </div>
  );
}
