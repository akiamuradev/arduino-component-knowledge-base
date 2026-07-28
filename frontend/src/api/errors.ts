import { ApiError } from "./client";

const ERROR_MESSAGES: Readonly<Record<string, string>> = {
  audit_date_range_invalid: "Проверьте диапазон дат журнала.",
  authentication_rate_limited: "Слишком много попыток. Подождите и попробуйте снова.",
  authentication_required: "Войдите, чтобы продолжить.",
  csrf_token_missing: "Сессия устарела. Обновите страницу и повторите действие.",
  csrf_validation_failed: "Сессия устарела. Обновите страницу и повторите действие.",
  invalid_credentials: "Неверный логин или пароль.",
  media_upload_failed: "Не удалось загрузить файл. Попробуйте снова.",
  network_unavailable: "Нет связи с сервисом. Проверьте подключение и попробуйте снова.",
  permission_denied: "Это действие недоступно для вашей роли.",
  revision_conflict: "Данные уже изменились. Обновите страницу и повторите действие.",
  validation_failed: "Проверьте заполнение полей.",
};

const PROCESSING_FAILURE_MESSAGES: Readonly<Record<string, string>> = {
  catalog_conflict: "Карточка конфликтует с уже сохранёнными данными.",
  image_magic_invalid: "Содержимое файла не соответствует формату изображения.",
  import_processing_failed: "Не удалось обработать данные компонента.",
  media_attempts_exhausted: "Не удалось обработать файл после нескольких попыток.",
  media_storage_failed: "Не удалось прочитать или сохранить файл.",
  media_storage_transient: "Хранилище файлов временно недоступно.",
  media_validation_failed: "Файл не прошёл проверку.",
};

export function userErrorMessage(
  error: unknown,
  fallback = "Не удалось выполнить действие. Попробуйте снова.",
): string {
  if (!(error instanceof ApiError)) return fallback;
  return ERROR_MESSAGES[error.code] ?? error.message;
}

export function isRetryableError(error: unknown): boolean {
  return error instanceof ApiError && error.retryable;
}

export function isPermissionError(error: unknown): boolean {
  return error instanceof ApiError
    && (error.status === 403 || error.code === "permission_denied");
}

export function processingFailureMessage(code: string | null | undefined): string {
  if (code === null || code === undefined) return "Ошибок нет.";
  return PROCESSING_FAILURE_MESSAGES[code] ?? "Не удалось завершить обработку.";
}
