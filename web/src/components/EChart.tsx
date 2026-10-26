import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";

export function useCssVar(name: string) {
  const [v, setV] = useState("");
  useEffect(() => {
    const read = () => setV(getComputedStyle(document.documentElement).getPropertyValue(name).trim());
    read();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", read);
    return () => mq.removeEventListener("change", read);
  }, [name]);
  return v;
}

/** 공통 차트 팔레트(테마 변수 기반). */
export function usePalette() {
  const ink = useCssVar("--ink"), ink2 = useCssVar("--ink-2"), ink3 = useCssVar("--ink-3"), line = useCssVar("--line");
  const up = useCssVar("--up"), down = useCssVar("--down"), surface = useCssVar("--surface");
  return { ink, ink2, ink3, line, up, down, surface };
}

export default function EChart({ option, height = 320 }: { option: object; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current);
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(ref.current);
    return () => { ro.disconnect(); chart.current?.dispose(); chart.current = null; };
  }, []);
  useEffect(() => { chart.current?.setOption(option as echarts.EChartsOption, true); }, [option]);
  return <div ref={ref} style={{ width: "100%", height }} role="img" />;
}
