interface ErrorMessageProps {
  message: string;
}

export const ErrorMessage = ({ message }: ErrorMessageProps) => (
  <p className="inline-error" role="alert">
    {message}
  </p>
);
