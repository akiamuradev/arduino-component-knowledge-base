import type {
  ComponentStatus,
  Difficulty,
  ImportRelationType,
  ImportReviewStatus,
  JobStatus,
} from "../api/contracts";

export const COMPONENT_STATUS_LABELS: Record<ComponentStatus, string> = {
  draft: "Черновик",
  in_review: "На проверке",
  changes_requested: "Требует исправлений",
  approved: "Одобрена",
  published: "Опубликована",
  hidden: "Скрыта",
  archived: "Архивирована",
};

export const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  beginner: "Начальный уровень",
  intermediate: "Средний уровень",
  advanced: "Продвинутый уровень",
};

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  queued: "В очереди",
  running: "Выполняется",
  retrying: "Ожидает повторного запуска",
  succeeded: "Завершена",
  failed: "Ошибка",
  cancelled: "Отменена",
};

export const IMPORT_REVIEW_STATUS_LABELS: Record<ImportReviewStatus, string> = {
  pending: "Ожидает проверки",
  confirmed: "Подтверждён",
};

export const IMPORT_RELATION_LABELS: Record<ImportRelationType, string> = {
  exact_component: "Тот же компонент",
  main_integrated_circuit: "Основная микросхема",
  onboard_component: "Компонент на плате",
  connector: "Разъём",
  functional_equivalent: "Функциональный аналог",
};

const TECHNICAL_VALUE_LABELS: Readonly<Record<string, string>> = Object.freeze({
  accept: "Принято",
  accepted: "Принято",
  approve: "Одобрено",
  approved: "Одобрено",
  confirmed: "Подтверждено",
  create: "Создание",
  exact: "Точное совпадение",
  high: "Высокая",
  low: "Низкая",
  medium: "Средняя",
  merge: "Объединение",
  pending: "Ожидает решения",
  reject: "Отклонено",
  rejected: "Отклонено",
  review: "Требуется проверка",
  selected: "Выбрано",
  warning: "Предупреждение",
});

export function technicalValueLabel(value: string): string {
  return TECHNICAL_VALUE_LABELS[value] ?? value;
}
