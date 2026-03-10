interface LoadingSpinnerProps {
  label?: string;
}

export const LoadingSpinner = ({ label = "Loading..." }: LoadingSpinnerProps) => (
  <div className="loading-spinner" role="status" aria-label={label}>
    <span className="spinner-ring" aria-hidden="true" />
    <span className="spinner-label">{label}</span>
  </div>
);
