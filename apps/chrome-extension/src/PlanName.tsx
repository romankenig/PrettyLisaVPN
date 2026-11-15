const emoji = {
  DEMO: "⏳",
  FREE: "🕊️",
  PREMIUM: "⭐",
  PLATINUM: "💎",
} as const;

export function PlanName({ plan }: { plan: string }) {
  const name = plan.toUpperCase();
  return (
    <span className="plan-name">
      {name} {emoji[name as keyof typeof emoji] ?? ""}
    </span>
  );
}
