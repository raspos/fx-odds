// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type J = any;

export const fmt = (v: number | null | undefined, d = 0) =>
  v == null || !isFinite(v) ? "–" : v.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
export const pct = (p: number | null | undefined, d = 1) => {
  if (p == null || !isFinite(p)) return "–";
  const v = p * 100;
  if (v < 0.1) return "<0.1%";
  if (v < 100 && v > 99.9) return ">99.9%";
  return v.toFixed(d) + "%";
};
export const sgn = (v: number | null | undefined, d = 2) => (v == null || !isFinite(v) ? "–" : (v >= 0 ? "+" : "") + v.toFixed(d));

/** 오름차순 x 격자 위에서 선형 보간. 범위 밖이면 null. */
export function interp(xs: number[], ys: number[], x: number): number | null {
  if (x < xs[0] || x > xs[xs.length - 1]) return null;
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] <= x) lo = m; else hi = m; }
  const t = (x - xs[lo]) / (xs[hi] - xs[lo] || 1);
  return ys[lo] + t * (ys[hi] - ys[lo]);
}

export const MODEL_SHORT: Record<string, string> = {
  A: "A 랜덤워크", B: "B 역사적 변동성", C: "C EWMA", D: "D 재표본추출",
  E0: "원·달러만", EJ: "+엔화", EC: "+위안화", ET: "+대만달러", E3: "+세 통화", EF: "+세 통화+달러요인", EP: "+압력지수(FPI)", ER: "+세 통화+달러요인+금리차(F)",
};

export function fisher(rho: number, n: number, k = 0): [number, number] {
  const z = Math.atanh(Math.max(-0.999, Math.min(0.999, rho))), se = 1 / Math.sqrt(Math.max(1, n - 3 - k));
  return [Math.tanh(z - 1.96 * se), Math.tanh(z + 1.96 * se)];
}
