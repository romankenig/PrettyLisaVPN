import type { HistoryNode, Measurement } from "./history.ts";

export type ChartMetric = "speed" | "rating" | "active";
export type Point = { time: number; value: number; covered?: number; total?: number };
export type Series = { nodeId: string; nodeName: string; direction: "download" | "upload" | "rating" | "active"; segments: Point[][] };

const HOUR = 3600000;
function valueOf(sample: Measurement, direction: Series["direction"]): number | null {
  const value = direction === "active" ? sample.active_connections : direction === "rating" ? sample.quality : direction === "download" ? sample.download_mbps : sample.upload_mbps;
  return value != null && Number.isFinite(value) && value >= 0 && (direction !== "active" || Number.isInteger(value)) ? value : null;
}

export function aggregateValues(values: number[], metric: ChartMetric): number | null {
  if (!values.length) return null;
  if (metric === "rating") {
    const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }
  const sum = values.reduce((total, value) => total + value, 0);
  return metric === "active" ? sum : sum / values.length;
}

/** Equal weight per server, not per check. No carry-forward across missing hours. */
export function aggregateSeries(nodes: HistoryNode[], metric: ChartMetric): Series[] {
  const hours = new Map<number, Map<string, Measurement>>();
  for (const node of nodes) for (const bucket of node.history) {
    const bucketTime = Date.parse(bucket.at);
    if (Number.isFinite(bucketTime) && !hours.has(bucketTime)) hours.set(bucketTime, new Map());
    for (const sample of bucket.measurements ?? []) {
      const time = Date.parse(sample.observed_at);
      if (!Number.isFinite(time)) continue;
      const hour = Math.floor(time / HOUR) * HOUR;
      const members = hours.get(hour) ?? new Map<string, Measurement>();
      const previous = members.get(node.id);
      if (!previous || time >= Date.parse(previous.observed_at)) members.set(node.id, sample);
      hours.set(hour, members);
    }
  }
  const directions: Series["direction"][] = metric === "speed" ? ["download", "upload"] : [metric];
  return directions.map(direction => {
    const segments: Point[][] = [];
    let segment: Point[] = [];
    for (const [time, members] of [...hours].sort(([a], [b]) => a - b)) {
      const values = [...members.values()].map(sample => valueOf(sample, direction)).filter((value): value is number => value !== null);
      const value = aggregateValues(values, metric);
      if (value === null) { segment = []; continue; }
      if (!segment.length || time - segment[segment.length - 1].time > HOUR) { segment = []; segments.push(segment); }
      segment.push({ time, value, covered: values.length, total: nodes.length });
    }
    return { nodeId: "aggregate", nodeName: "Выбранные серверы", direction, segments };
  });
}

/** One bar per node/hour: the last measured count, never a sum of repeated probes. */
export function activeBars(series: Series[]) {
  return series.flatMap(line => {
    const hours = new Map<number, Point>();
    for (const point of line.segments.flat()) {
      const hour = Math.floor(point.time / 3600000) * 3600000;
      const previous = hours.get(hour);
      if (!previous || point.time >= previous.time) hours.set(hour, point);
    }
    return [...hours].sort(([a], [b]) => a - b).map(([hour, point]) => ({
      nodeId: line.nodeId, nodeName: line.nodeName, hour, ...point,
    }));
  });
}

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
