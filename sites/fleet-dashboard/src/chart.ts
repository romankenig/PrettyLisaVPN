import type { HistoryNode } from "./history.ts";

export type ChartMetric = "speed" | "rating";
export type Point = { time: number; value: number };
export type Series = { nodeId: string; nodeName: string; direction: "download" | "upload" | "rating"; segments: Point[][] };

export function chartSeries(nodes: HistoryNode[], metric: ChartMetric): Series[] {
  return nodes.flatMap(node => {
    const samples = node.history.flatMap(hour => hour.measurements ?? []).sort((a, b) => a.observed_at.localeCompare(b.observed_at));
    const directions = metric === "speed" ? ["download", "upload"] as const : ["rating"] as const;
    return directions.map(direction => {
      const segments: Point[][] = [];
      let segment: Point[] = [];
      for (const sample of samples) {
        const value = direction === "rating" ? sample.quality : direction === "download" ? sample.download_mbps : sample.upload_mbps;
        const time = Date.parse(sample.observed_at);
        if (value == null || !Number.isFinite(value) || !Number.isFinite(time)) {
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
