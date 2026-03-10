interface StatCardProps {
  label: string;
  value: string | number;
  tone?: "neutral" | "accent" | "warm";
}

export const StatCard = ({ label, value, tone = "neutral" }: StatCardProps) => (
  <article className={`stat-card tone-${tone}`}>
    <span>{label}</span>
    <strong>{value}</strong>
  </article>
);
