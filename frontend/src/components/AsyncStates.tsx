interface LoadingStateProps {
  label?: string;
}

export function LoadingState({ label = "Загрузка…" }: LoadingStateProps) {
  return (
    <div className="state-card" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = "Не удалось загрузить данные",
  message,
  onRetry,
}: ErrorStateProps) {
  return (
    <section className="state-card state-card--error" role="alert">
      <p className="eyebrow">Ошибка</p>
      <h1>{title}</h1>
      <p>{message}</p>
      {onRetry === undefined ? null : (
        <button className="button button--primary" type="button" onClick={onRetry}>
          Повторить
        </button>
      )}
    </section>
  );
}
