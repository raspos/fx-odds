import { J } from "../lib";

const Item = ({ n, t, children }: { n: number; t: string; children: React.ReactNode }) => (
  <details className="border-b py-2.5" style={{ borderColor: "var(--line)" }}>
    <summary className="cursor-pointer text-[14px] font-semibold"><span className="num mr-2" style={{ color: "var(--ink-3)" }}>{String(n).padStart(2, "0")}</span>{t}</summary>
    <div className="mt-2 space-y-1.5 pl-7 text-[13px] leading-relaxed" style={{ color: "var(--ink-2)" }}>{children}</div>
  </details>
);
const Code = ({ children }: { children: React.ReactNode }) => (
  <code className="num block overflow-x-auto rounded-md px-2.5 py-1.5 text-[12px]" style={{ background: "var(--surface-2)", color: "var(--ink)" }}>{children}</code>
);

export const STATUS: [string, string, string][] = [
  ["USD/KRW 7일·30일 확률 전망 (모형 A~D)", "구현", "ECOS 매매기준율, 일별 갱신"],
  ["분포 차트·구간 확률표·도달 확률 계산기·기간 중 돌파 확률", "구현", "브라운 다리 보정 포함"],
  ["원화 동조화 레이더 (20·60·120·252일, 달러요인 통제, 선행·후행, Granger, 예측 기여도)", "구현", "Yahoo 단일 출처(비공식), 전 거래일까지"],
  ["FX SCORECARD (MAE·RMSE·포함률·Brier·CRPS·DM 검정)", "구현", "2012~ Walk-forward, 다운로드 제공"],
  ["과거 시점 재현 (HISTORICAL MODE)", "일부", "환율 전망·동조화만. 당시 뉴스·FPI는 보존 자료 없음"],
  ["조건부 모형 E (원화+해외통화+달러요인)", "실험", "백테스트에서 개선이 확인되지 않아 공식 전망 미반영"],
  ["금리를 통제한 조건부 모형 (F: 세 통화+달러요인+한미 금리차)", "실험", "백테스트에서 개선 미확인 → 공식 전망 미반영"],
  ["입수 자료 보강: 지정학 위험지수(GPR), 일본·중국·미국 정책금리, 외국인 주식 순매수(월)", "구현", "FPI·사건에 반영. 외국인 코스피·코스닥 일별 순매수는 KIS 키 등록 후 수집, 채권 일별·컨센서스는 미보유"],
  ["FX PRESSURE INDEX (10개 요인, 자료 충족률)", "실험", "규칙 기반. 방향 예측력 미확인 → 확률 전망 미반영"],
  ["시장 사건 타임라인 (정책금리·급변동, 사건 그룹)", "구현", "통계 추출 + 전후 1일 관련 기사 링크(후보)"],
  ["뉴스 압력 지수(NPI, 네이버 제목 기반 인과 규칙)", "실험", "검증 전 · 확률 전망 미반영 · 매일 기록 중"],
  ["공식 보고서·발표 목록 (한국은행·연준·BIS)", "구현", "제목·링크만, 방향 단정 없음"],
  ["FX SCENARIO (시나리오 분석기)", "미구현", "추정 계수가 없어 임의 변경하지 않음"],
  ["통합 전망 C (정량+정성)", "미구현", "FPI·뉴스 점수가 생긴 뒤 백테스트로 검증"],
  ["교차검증 (Yahoo ↔ ECOS 원/달러)", "구현", "메타 데이터 참조"],
];

export default function Methodology({ meta }: { meta: J }) {
  const cc = meta.cross_check;
  return (
    <div className="space-y-4">
      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">구현 상태</h3>
        <div className="scrollx mt-2">
          <table className="t"><thead><tr><th>기능</th><th>상태</th><th>비고</th></tr></thead>
            <tbody>{STATUS.map(([a, b, c]) => (<tr key={a}><td style={{ whiteSpace: "normal" }}>{a}</td><td><b>{b}</b></td><td style={{ whiteSpace: "normal", textAlign: "left" }}>{c}</td></tr>))}</tbody></table>
        </div>
      </div>
      <div className="card p-4 sm:p-5">
        <h3 className="text-lg font-bold">계산 방법 공개</h3>
        <Item n={1} t="데이터 출처">
          <p><b>ECOS</b> 731Y001 원/미국달러·원/위안·원/100엔·원/대만달러 매매기준율(서울 기준) — 전망의 기준 시계열.</p>
          <p><b>Yahoo Finance</b> 일봉 마감(비공식·무료) — 동조화 레이더의 원·엔·위안·대만달러와 달러요인(단일 출처, 같은 시각 관측). 수집 실패 시 해당 항목은 비어 있으며 대체값을 만들지 않습니다.</p>
          <p>적재 규칙: 양수가 아닌 값, 주말 행 제거. 출처를 섞어 한 시계열로 합치지 않습니다.</p>
        </Item>
        <Item n={2} t="환율 가격 정의와 방향">
          <p>전망 대상: <b>달러당 원화값</b>(원/달러 매매기준율). 상승 = 원화 약세, 하락 = 원화 강세. 레이더의 모든 통화는 <b>USD 1단위당 외화</b>로 방향을 통일합니다(EUR·GBP·AUD는 원자료의 역수). 100엔 단위 환율은 100으로 나눠 환산합니다.</p>
          <p>달력일 기준 7일·30일 후가 목표일. 목표일이 휴장일·주말이면 <b>그 이전 마지막 거래일</b>의 매매기준율로 평가합니다. 변동성 스케일에는 기준일~목표일의 평일 수(7일→5, 30일→21~22)를 씁니다.</p>
        </Item>
        <Item n={3} t="데이터 갱신 시각"><p>하루 1회 한국시간 정규 배치. 화면 상단의 '최종 갱신'과 각 자료의 마지막 관측일을 확인하세요. 수집 실패 시 이전 정상 데이터를 유지하고 경고를 표시합니다.</p></Item>
        <Item n={4} t="로그수익률"><Code>r_t = ln(S_t / S_(t−1)),  R(h) = Σ r (h영업일 합)</Code></Item>
        <Item n={5} t="변동성 추정">
          <Code>A: σ = √(E[r²]) 전체 역사(2000~) · B: σ = std(r, 최근 252일) · C: σ²_t = 0.94·σ²_(t−1) + 0.06·r²_t</Code>
          <p>모형 D(FHS): 최근 1,500일의 표준화 잔차 z = r_t/σ_(C,t−1)를 복원추출해 h개를 합산하고 현재 σ_C를 곱합니다. 두꺼운 꼬리가 반영됩니다.</p>
        </Item>
        <Item n={6} t="확률분포"><Code>A~C: R(h) ~ N(0, σ²h) · 가격 S_T = S_0·exp(R) · D: 표본 40,000개</Code><p>drift는 0으로 둡니다. 모든 모형의 상승확률이 50% 근처인 이유입니다.</p></Item>
        <Item n={7} t="구간별 확률"><p>50%·80%·90% 구간은 25–75%, 10–90%, 5–95% 분위수입니다. 구간별 확률은 누적분포(CDF)의 차이로 계산해 합이 100%가 됩니다.</p></Item>
        <Item n={8} t="장벽(기간 중 돌파) 확률">
          <p>일별 경로 20,000개를 시뮬레이션해 최대·최소가 기준을 넘었는지 셉니다(이산 감시). 거래일 사이의 돌파를 놓치므로, 구간 끝점 사이의 브라운 다리 통과확률로 보정한 값을 기본 표시합니다.</p>
          <Code>P(구간 중 통과) = exp(−2(b−x_i)(b−x_(i+1)) / σ²)  →  P(touch) = 1 − E[Π(1−p_i)]</Code>
          <p>정규·무드리프트에서 이 값은 반사원리 2·P(R_h ≥ b)와 일치함을 테스트로 확인합니다. 모형 D에는 σ_C를 쓴 근사입니다. 일중(intraday) 고저가 돌파와는 다릅니다.</p>
        </Item>
        <Item n={9} t="이동상관계수"><p>20·60·120·252 거래일 창의 피어슨 상관(일별 로그수익률). 95% 신뢰구간은 Fisher z 변환(<span className="num">1/√(n−3)</span>).</p></Item>
        <Item n={10} t="달러 공통요인 통제">
          <p>요인 F = EUR·GBP·AUD·CAD·CHF·SEK의 USD당 로그수익률 평균(달러 강세 = +). 원화와 통화 X의 <b>부분상관</b>:</p>
          <Code>ρ(K,X·F) = (ρ_KX − ρ_KF·ρ_XF) / √((1−ρ²_KF)(1−ρ²_XF))</Code>
          <p>창 안의 자료만 사용합니다. DXY는 엔화를 포함하고 요인 구성이 유럽 편중이므로 사용하지 않았습니다. 요인 통제가 모든 공통 충격을 제거하지는 못합니다.</p>
        </Item>
        <Item n={11} t="선행·후행 분석">
          <p>corr(KRW_t, X_(t−k)), k = 0,1,2,3,5 및 반대 방향. 최근 1년·3년, 원화 변동성 상위 25%(불안기)·평시로 나눠 봅니다. Granger 검정(시차 1~5)은 예측 정보 추가 여부만 보며 인과관계가 아닙니다.</p>
          <p>관측 시각: 레이더는 Yahoo 일봉(런던 자정 마감) 단일 출처라 네 통화가 같은 시각입니다. 예측 기여도 검증은 서울 기준일 직전 영업일 해외 마감만 사용해 미래 정보를 배제합니다. 관측 시각을 맞출 수 없는 선행관계는 공식 결과로 표시하지 않습니다.</p>
        </Item>
        <Item n={12} t="예측 모형 가중치">
          <p>공식 전망 = 실현이 확정된 예측의 평균 CRPS가 가장 낮은 모형(A~D). 선택은 기준일마다 그때까지 실현된 예측만으로 다시 하며(과거 날짜 재현 시 미래 정보 배제), 표본이 250개 미만이면 C를 씁니다.</p>
          <p>조건부 모형: 목표(h일 로그수익률)를 [원화 5·20일 수익률, 해외 통화 5·20일 수익률, 달러요인]에 릿지(α = 훈련 표본 수, 강한 수축)로 회귀. 21영업일마다 재추정, 훈련 표본은 목표일이 기준일 이전인 것만. 분산은 EWMA를 그대로 씁니다.</p>
        </Item>
        <Item n={13} t="FPI 점수 계산"><p><b>미구현.</b> 점수는 확률이 아니며, 가중치가 검증되기 전에는 '실험적 압력 지수'로만 표시할 예정입니다. 결측은 0점으로 채우지 않고 자료 충족률을 함께 표시합니다.</p></Item>
        <Item n={14} t="보고서·뉴스 분석"><p>네이버 뉴스 검색(제목·링크만 저장)을 인과 규칙(예: 외국인 매도 → 원화 약세)으로 분류합니다. 같은 날 같은 주제는 하나의 사건 그룹(강도 max, 기사 수 무관), 상반 신호·부정 표현은 판단 유보, 환율 결과 보도는 점수 제외. 뉴스 압력 지수 = 100·tanh(Σ방향·강도·0.5^(경과일/7)/15). 과거 뉴스 보존본이 없어 백테스트하지 못했고 매일 기록해 공개 검증합니다. LLM은 사용하지 않습니다. API 키가 없어도 확률 전망과 레이더는 동작합니다.</p></Item>
        <Item n={15} t="백테스트">
          <p>2012-01부터 모든 영업일을 기준일로 Walk-forward. 지표: MAE, RMSE, 방향 적중률, 50/80/90% 포함률, Brier, CRPS(정규모형 해석해·표본모형 에너지 추정), 랜덤워크 대비 개선율, Newey-West DM 검정.</p>
          <p>한계: 과거 자료로 재계산한 결과이며 변동성·모형 형태를 정할 때 이 기간의 경험이 반영되었을 수 있습니다. 실시간 성적은 별도 기록(live_forecasts.csv)에 쌓입니다.</p>
        </Item>
        <Item n={16} t="모형 한계">
          <ul className="list-disc pl-5">
            <li>drift 0 · 변동성만 추정하는 모형이라 방향 예측력이 없습니다.</li>
            <li>정규 꼬리(A~C)는 급변(위기)을 과소평가합니다. 80%·90% 구간 포함률이 명목보다 낮을 수 있습니다.</li>
            <li>구간 환율 범위가 휴장일 수·정책 이벤트(금통위·FOMC) 일정을 반영하지 않습니다.</li>
            <li>상관관계는 인과관계가 아니며, 동시 동조화는 미래 예측력과 별개입니다.</li>
            <li>통계적 확률은 옵션시장 내재확률과 다릅니다. 이 서비스는 옵션 내재분포를 사용하지 않습니다.</li>
          </ul>
        </Item>
        <Item n={17} t="변경 이력"><p><b>v0.1.0</b> (2026-10-26) 최초 공개: 확률 전망 A~D, 동조화 레이더, 성적표, 과거 시점 재현(일부).</p></Item>
      </div>
      <div className="card p-4 text-[12px] leading-relaxed sm:p-5" style={{ color: "var(--ink-2)" }}>
        <h3 className="text-lg font-bold" style={{ color: "var(--ink)" }}>개념 구분</h3>
        <ul className="mt-1 list-disc space-y-1 pl-5">
          <li><b>상관 ≠ 인과.</b> 높은 상관계수는 함께 움직였다는 뜻일 뿐, 한 통화가 원화를 움직였다는 뜻이 아닙니다.</li>
          <li><b>동시 동조화 ≠ 미래 예측력.</b> 같은 날의 움직임이 같아도 내일의 환율을 맞히는 데는 도움이 되지 않을 수 있습니다(예측 기여도 표 참조).</li>
          <li><b>통계적 확률 ≠ 옵션 내재확률.</b> 여기 확률은 과거 수익률 분포에서 나온 값입니다.</li>
          <li><b>정성적 압력 ≠ 상승·하락 확률.</b> 압력 지수(미구현)는 확률이 아닙니다.</li>
          <li><b>백테스트 ≠ 실시간 성적.</b> 두 기록은 분리해 공개합니다.</li>
        </ul>
        <h3 className="mt-4 text-lg font-bold" style={{ color: "var(--ink)" }}>출처 간 교차검증 (최근 2년)</h3>
        <div className="scrollx">
          <table className="t"><thead><tr><th>비교</th><th>일치 일수</th><th>평균 차이</th><th>평균 절대 차이</th><th>일별 수익률 상관(ECOS 기준, 해외 시차 −1/0/+1일)</th></tr></thead>
            <tbody>{(["yahoo"] as const).map((k) => (<tr key={k}><td>ECOS vs Yahoo</td><td className="num">{cc[k].n}</td><td className="num">{cc[k].mean_diff_pct}%</td><td className="num">{cc[k].mean_abs_diff_pct}%</td>
              <td className="num">{cc[k].ret_corr_by_shift["-1"]} / {cc[k].ret_corr_by_shift["0"]} / {cc[k].ret_corr_by_shift["1"]}</td></tr>))}</tbody></table>
        </div>
        <p className="mt-1">ECOS(서울 오후)와 Yahoo(런던 자정)는 관측 시각이 달라 같은 날 수준이 약간 다르고, 수익률 상관이 시차 +1일에서 가장 높은 것은 해외 시장의 움직임이 서울의 다음 거래일에 반영되기 때문입니다. 그래서 이 서비스는 같은 날짜 자료를 같은 시각의 가격으로 취급하지 않고 출처·시각을 분리합니다.</p>
      </div>
    </div>
  );
}
