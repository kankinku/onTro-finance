interface StatusPillProps {
  label: string;
  tone?: "neutral" | "success" | "warning";
}

export const StatusPill = ({ label, tone = "neutral" }: StatusPillProps) => (
  <span className={`status-pill tone-${tone}`}>{label}</span>
);
