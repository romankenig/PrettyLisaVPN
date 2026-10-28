export type Measurement = {
  observed_at: string; status: string; mode: string; quality: number | null;
  download_mbps: number | null; upload_mbps: number | null;
  connection_ms: number | null; active_connections: number;
};
export type FocusedHour = { at: string; nodeId?: string };
export type HistoryNode = { id: string; name: string; history: { at: string; measurements?: Measurement[] }[] };

export function hourMeasurements(nodes: HistoryNode[], focus: FocusedHour) {
  return nodes.filter(node => !focus.nodeId || node.id === focus.nodeId).flatMap(node =>
    (node.history.find(hour => Date.parse(hour.at) === Date.parse(focus.at))?.measurements ?? []).map(value => ({ ...value, nodeId: node.id, nodeName: node.name }))
  ).sort((a, b) => a.observed_at.localeCompare(b.observed_at) || a.nodeName.localeCompare(b.nodeName));
}
