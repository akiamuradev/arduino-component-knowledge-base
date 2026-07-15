import { useState } from "react";

import type { JobStatus } from "../api/contracts";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { useAdminJobs, useRetryJob } from "../jobs/queries";

const statuses: { value: JobStatus | "all"; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "queued", label: "В очереди" },
  { value: "running", label: "Выполняются" },
  { value: "retrying", label: "Ожидают retry" },
  { value: "failed", label: "Ошибки" },
  { value: "succeeded", label: "Завершены" },
];

export function AdminJobsPage() {
  const [status, setStatus] = useState<JobStatus | "all">("all");
  const jobs = useAdminJobs(status === "all" ? undefined : status);
  const retry = useRetryJob();

  if (jobs.isPending) {
    return <LoadingState label="Загружаем фоновые задачи…" />;
  }
  if (jobs.isError) {
    return (
      <ErrorState
        title="Монитор задач недоступен"
        message="Backend не вернул durable job state. Ошибка не заменена локальными данными."
        onRetry={() => {
          void jobs.refetch();
        }}
      />
    );
  }

  return (
    <section>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Только administrator</p>
          <h2>Фоновые задачи</h2>
        </div>
        <label className="job-filter">
          Статус
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as JobStatus | "all");
            }}
          >
            {statuses.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>
      <p className="lede">
        PostgreSQL является источником статуса. Список обновляется каждые пять секунд;
        очистка Redis не превращает failed job в successful.
      </p>
      {retry.isError ? <p className="form-error" role="alert">Не удалось поставить задачу повторно.</p> : null}
      {jobs.data.items.length === 0 ? (
        <p className="empty-panel">Задач с выбранным статусом нет.</p>
      ) : (
        <div className="job-table" aria-label="Фоновые задачи">
          {jobs.data.items.map((job) => (
            <article className="job-row" key={job.id}>
              <div>
                <strong>{job.task_name}</strong>
                <small>{job.kind} · {job.queue_name} · {job.id.slice(0, 8)}</small>
              </div>
              <span className={`status-badge status-badge--${job.status}`}>{job.status}</span>
              <div className="job-progress">
                <span>{job.phase} · {job.progress_percent}%</span>
                <progress max={100} value={job.progress_percent}>{job.progress_percent}%</progress>
              </div>
              <span>{job.attempts}/{job.max_attempts}</span>
              <span className="job-error">{job.error_code ?? "—"}</span>
              {job.status === "failed" ? (
                <button
                  className="button button--quiet"
                  disabled={retry.isPending}
                  type="button"
                  onClick={() => {
                    retry.mutate(job.id);
                  }}
                >
                  Повторить
                </button>
              ) : <span />}
            </article>
          ))}
        </div>
      )}
      <p className="muted">Всего: {jobs.data.total}</p>
    </section>
  );
}
