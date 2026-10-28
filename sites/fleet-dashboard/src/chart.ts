import type { HistoryNode } from "./history.ts";

export type ChartMetric = "speed" | "rating" | "active";
export type Point = { time: number; value: number };
export type Series = { nodeId: string; nodeName: string; direction: "download" | "upload" | "rating" | "active"; segments: Point[][] };

export function chartSeries(nodes: HistoryNode[], metric: ChartMetric): Series[] {
  return nodes.flatMap(node => {
    const samples = node.history.flatMap(hour => hour.measurements ?? []).sort((a, b) => a.observed_at.localeCompare(b.observed_at));
    const directions: Series["direction"][] = metric === "speed" ? ["download", "upload"] : [metric];
    return directions.map(direction => {
      const segments: Point[][] = [];
      let segment: Point[] = [];
      for (const sample of samples) {
        const value = direction === "active" ? sample.active_connections : direction === "rating" ? sample.quality : direction === "download" ? sample.download_mbps : sample.upload_mbps;
        const time = Date.parse(sample.observed_at);
        if (value == null || !Number.isFinite(value) || !Number.isFinite(time) || (direction === "active" && (!Number.isInteger(value) || value < 0))) {
          segment = []; continue;
        }
        if (!segment.length || time - segment[segment.length - 1].time > 75 * 60 * 1000) {
          segment = []; segments.push(segment);
        }
        segment.push({ time, value });
      }
      return { nodeId: node.id, nodeName: node.name, direction, segments };
    });
  });
}
