import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer]);

export interface Series {
  name: string;
  values: number[];
  type?: "bar" | "line";
  color?: string;
}

const PALETTE = ["#0b2e59", "#e07b00", "#136b35", "#6b737c", "#b3261e"];

/**
 * Chart with an equivalent data table for screen-reader and keyboard users
 * (the chart itself is hidden from assistive technology).
 */
export function Chart({ title, categories, series, horizontal = false, height = 280 }: {
  title: string; categories: string[]; series: Series[]; horizontal?: boolean; height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || typeof window === "undefined" || !("ResizeObserver" in window)) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "svg" });
    const catAxis = { type: "category" as const, data: categories, axisLabel: { color: "#1d2125", fontSize: 11, width: horizontal ? 200 : 80, overflow: "break" as const } };
    const valAxis = { type: "value" as const, minInterval: 1, axisLabel: { color: "#1d2125" } };
    chart.setOption({
      animation: false,
      color: series.map((s, i) => s.color ?? PALETTE[i % PALETTE.length] ?? "#0b2e59"),
      tooltip: { trigger: "axis" },
      legend: series.length > 1 ? { top: 0, textStyle: { color: "#1d2125" } } : undefined,
      grid: { left: 12, right: 16, top: series.length > 1 ? 32 : 12, bottom: 24, containLabel: true },
      xAxis: horizontal ? valAxis : catAxis,
      yAxis: horizontal ? catAxis : valAxis,
      series: series.map((s) => ({ name: s.name, type: s.type ?? "bar", data: s.values, barMaxWidth: 28 })),
    });
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [categories, series, horizontal]);

  return (
    <figure className="m-0">
      <div ref={ref} style={{ height }} aria-hidden="true" />
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-link underline">Show data table: {title}</summary>
        <table className="mt-2 w-full border-collapse text-left">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr>
              <th scope="col" className="border-b border-line px-2 py-1">Category</th>
              {series.map((s) => (
                <th key={s.name} scope="col" className="border-b border-line px-2 py-1 text-right">{s.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {categories.map((c, i) => (
              <tr key={`${c}-${i}`}>
                <th scope="row" className="border-b border-line px-2 py-1 font-normal">{c}</th>
                {series.map((s) => (
                  <td key={s.name} className="border-b border-line px-2 py-1 text-right">{s.values[i] ?? 0}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
