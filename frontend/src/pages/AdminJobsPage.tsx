import { useState } from "react";
import { Link } from "react-router-dom";

import type { JobStatus } from "../api/contracts";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { SplatEmptyState } from "../components/SplatEmptyState";
import {
  useAdminImportJobs,
  useAdminJobs,
  useRetryImportJob,
  useRetryJob,
} from "../jobs/queries";

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
  const importJobs = useAdminImportJobs(status === "all" ? undefined : status);
  const retry = useRetryJob();
  const retryImport = useRetryImportJob();

  if (jobs.isPending || importJobs.isPending) {
    return <LoadingState label="Загружаем фоновые задачи…" />;
  }
  if (jobs.isError || importJobs.isError) {
    return (
      <ErrorState
        title="Монитор задач недоступен"
        message="Backend не вернул durable job state. Ошибка не заменена локальными данными."
        onRetry={() => {
          void Promise.all([jobs.refetch(), importJobs.refetch()]);
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
      {retryImport.isError ? <p className="form-error" role="alert">Не удалось повторить импорт.</p> : null}
      <div className="section-heading"><div><p className="section-kicker">Import jobs</p><h3>Импорт карточек</h3></div><span>{importJobs.data.total}</span></div>
      {importJobs.data.items.length === 0 ? (
        <p className="muted">Задач импорта для выбранного статуса нет.</p>
      ) : (
        <div className="job-table" aria-label="Задачи импорта">
          {importJobs.data.items.map((job) => (
            <article className="job-row" key={job.id}>
              <div>
                <strong>{job.source_entry_name ?? job.source_file_path ?? "Repository import"}</strong>
                <small>import · imports · {job.id.slice(0, 8)}</small>
              </div>
              <span className={`status-badge status-badge--${job.status}`}>{job.status}</span>
              <div className="job-progress">
                <span>{job.repository_url ?? "repository"}</span>
                {job.draft_component_id === null ? null : <Link to={`/admin/components/${job.draft_component_id}/edit`}>Открыть draft</Link>}
              </div>
              <span>{job.attempts}/{job.max_attempts}</span>
              <span className="job-error">{job.error_code ?? "—"}</span>
              {job.retryable ? (
                <button
                  className="button button--quiet"
                  disabled={retryImport.isPending}
                  type="button"
                  onClick={() => {
                    retryImport.mutate(job.id);
                  }}
                >
                  Повторить
                </button>
              ) : <span />}
            </article>
          ))}
        </div>
      )}
      <div className="section-heading"><div><p className="section-kicker">Media jobs</p><h3>Обработка медиа</h3></div><span>{jobs.data.total}</span></div>
      {jobs.data.items.length === 0 && importJobs.data.items.length === 0 ? (
        <SplatEmptyState icon="↻" title="Задач пока нет" description="Для выбранного статуса фоновые задачи отсутствуют." />
      ) : jobs.data.items.length === 0 ? (
        <p className="muted">Задач обработки медиа для выбранного статуса нет.</p>
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
      <p className="muted">Всего: {jobs.data.total + importJobs.data.total}</p>
    </section>
  );
}
