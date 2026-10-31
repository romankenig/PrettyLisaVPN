import { aggregateValues, type ChartMetric } from "./chart.ts";
import { nodeGroup, type Group } from "./groups.ts";

type SummaryNode = { group?: Group; quality: number; latest: { download_mbps: number | null; upload_mbps: number | null; active_connections: number } | null };
export function selectionSummary(nodes: SummaryNode[]) {
  const metric = (read: (node: SummaryNode) => number | null | undefined, kind: ChartMetric) => {
    const members = kind === "active" ? nodes.filter(node => nodeGroup(node) !== "INTERMEDIATE") : nodes;
    const values = members.filter(node => node.latest !== null).map(read).filter((value): value is number => value != null && Number.isFinite(value) && value >= 0 && (kind !== "active" || Number.isInteger(value)));
    return { value: aggregateValues(values, kind), covered: values.length, total: members.length };
  };
  return {
    download: metric(node => node.latest?.download_mbps, "speed"),
    upload: metric(node => node.latest?.upload_mbps, "speed"),
    rating: metric(node => node.quality, "rating"),
    active: metric(node => node.latest?.active_connections, "active"),
  };
}
