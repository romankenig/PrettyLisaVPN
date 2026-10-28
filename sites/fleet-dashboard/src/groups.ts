export const GROUPS = ["INTERMEDIATE", "FREE", "PREMIUM"] as const;
export type Group = typeof GROUPS[number];
export const groupNames: Record<Group, string> = { INTERMEDIATE: "Промежуточные", FREE: "FREE", PREMIUM: "PREMIUM" };
type SummaryNode = { group?: Group; is_available_for_free?: boolean; available: boolean; known_hours: number; successful_hours: number; latest: { active_connections: number } | null };
export const nodeGroup = (node: Pick<SummaryNode, "group" | "is_available_for_free">): Group => node.group ?? (node.is_available_for_free ? "FREE" : "PREMIUM");
export function groupSummaries(nodes: SummaryNode[]) {
  return GROUPS.map(group => {
    const members = nodes.filter(node => nodeGroup(node) === group);
    const known = members.reduce((sum, node) => sum + node.known_hours, 0);
    const successful = members.reduce((sum, node) => sum + node.successful_hours, 0);
    return { group, servers: members.length, available: members.filter(node => node.available).length,
      active: members.reduce((sum, node) => sum + (node.latest?.active_connections ?? 0), 0),
      availability: known ? 100 * successful / known : null };
  });
}
