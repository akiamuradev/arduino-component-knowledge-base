import { useState } from "react";
import { Link } from "react-router-dom";

import { processingFailureMessage, userErrorMessage } from "../api/errors";
import type { JobStatus } from "../api/contracts";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { SplatEmptyState } from "../components/SplatEmptyState";
import { JOB_STATUS_LABELS } from "../config/uiLabels";
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
  { value: "retrying", label: "Ожидают повторного запуска" },
  { value: "failed", label: "Ошибки" },
  { value: "succeeded", label: "Завершены" },
];

const phaseLabels: Readonly<Record<string, string>> = {
  queued: "Ожидает запуска",
  starting: "Запускается",
  downloading: "Получение файла",
  probing: "Проверка файла",
  transcoding: "Подготовка версии для просмотра",
  poster: "Подготовка обложки",
  uploading: "Сохранение результата",
  retrying: "Ожидает повторной попытки",
  completed: "Готово",
  failed: "Обработка остановлена",
};

function mediaTitle(kind: "image" | "video"): string {
  return kind === "video" ? "Обработка видео" : "Обработка изображения";
}

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
        message={userErrorMessage(
          jobs.error ?? importJobs.error,
          "Не удалось загрузить состояние обработки. Попробуйте снова.",
        )}
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
          <p className="eyebrow">Только для администратора</p>
          <h2>Диагностика обработки</h2>
        </div>
        <label className="job-filter">
          Состояние
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
        Здесь показано сохранённое состояние импорта и обработки файлов. Список обновляется
        автоматически каждые пять секунд.
      </p>
      {retry.isError ? <p className="form-error" role="alert">{userErrorMessage(retry.error, "Не удалось повторить обработку файла. Попробуйте снова.")}</p> : null}
      {retryImport.isError ? <p className="form-error" role="alert">{userErrorMessage(retryImport.error, "Не удалось повторить импорт. Попробуйте снова.")}</p> : null}
      <div className="section-heading"><div><p className="section-kicker">Задачи импорта</p><h3>Импорт карточек</h3></div><span>{importJobs.data.total}</span></div>
      {importJobs.data.items.length === 0 ? (
        <SplatEmptyState icon="✓" title="Импортов пока нет" description="Для выбранного состояния нет сохранённых загрузок." />
      ) : (
        <div className="job-table" aria-label="Задачи импорта">
          {importJobs.data.items.map((job) => (
            <article className="job-row" key={job.id}>
              <div>
                <strong>{job.source_entry_name ?? job.source_file_path ?? "Импорт из репозитория"}</strong>
                <small>Импорт компонента · {job.id.slice(0, 8)}</small>
              </div>
              <span className={`status-badge status-badge--${job.status}`}>{JOB_STATUS_LABELS[job.status]}</span>
              <div className="job-progress">
                <span>{job.repository_url ?? "Репозиторий не указан"}</span>
                {job.draft_component_id === null ? null : <Link to={`/admin/components/${job.draft_component_id}/edit`}>Открыть черновик</Link>}
              </div>
              <span>Попытка {job.attempts} из {job.max_attempts}</span>
              <span className="job-error">{processingFailureMessage(job.error_code)}</span>
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
      <div className="section-heading"><div><p className="section-kicker">Задачи обработки файлов</p><h3>Обработка медиа</h3></div><span>{jobs.data.total}</span></div>
      {jobs.data.items.length === 0 && importJobs.data.items.length === 0 ? (
        <SplatEmptyState icon="↻" title="Задач пока нет" description="Для выбранного статуса фоновые задачи отсутствуют." />
      ) : jobs.data.items.length === 0 ? (
        <SplatEmptyState icon="✓" title="Файлов в обработке нет" description="Для выбранного состояния задачи обработки файлов отсутствуют." />
      ) : (
        <div className="job-table" aria-label="Диагностика фоновых задач">
          {jobs.data.items.map((job) => (
            <article className="job-row" key={job.id}>
              <div>
                <strong>{mediaTitle(job.kind)}</strong>
                <small>{job.kind === "video" ? "Видео" : "Изображение"} · {job.id.slice(0, 8)}</small>
              </div>
              <span className={`status-badge status-badge--${job.status}`}>{JOB_STATUS_LABELS[job.status]}</span>
              <div className="job-progress">
                <span>{phaseLabels[job.phase] ?? "Обработка"} · {job.progress_percent}%</span>
                <progress max={100} value={job.progress_percent}>{job.progress_percent}%</progress>
              </div>
              <span>Попытка {job.attempts} из {job.max_attempts}</span>
              <span className="job-error">{processingFailureMessage(job.error_code)}</span>
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
