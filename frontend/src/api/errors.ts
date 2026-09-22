import { ApiError } from "./client";

export interface ValidationIssue {
  path: (string | number)[];
  code: string;
  meta: Record<string, unknown>;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function validationIssues(error: unknown): ValidationIssue[] {
  if (!(error instanceof ApiError) || error.code !== "validation_failed") return [];
  const issues = error.details?.issues;
  if (!Array.isArray(issues)) return [];
  return issues.slice(0, 50).flatMap((value: unknown): ValidationIssue[] => {
    if (!record(value) || typeof value.code !== "string" || !/^[a-z][a-z0-9_]{0,79}$/.test(value.code)
      || !Array.isArray(value.path) || value.path.length === 0 || value.path.length > 8
      || !value.path.every((part: unknown) => (typeof part === "string" && part.length <= 100)
        || (typeof part === "number" && Number.isSafeInteger(part) && part >= 0))) return [];
    return [{ path: value.path as (string | number)[], code: value.code,
      meta: record(value.meta) ? value.meta : {} }];
  });
}

export function validationIssueMessage(issue: ValidationIssue): string {
  const text = (key: string, fallback: string) => typeof issue.meta[key] === "string"
    ? issue.meta[key].slice(0, 160) : fallback;
  const label = text("label", "характеристики");
  const unit = text("expected_unit", "");
  switch (issue.code) {
    case "slug_already_exists": return "Этот адрес страницы уже занят. Укажите другой.";
    case "slug_change_forbidden": return "Адрес уже опубликованной карточки нельзя изменить.";
    case "incompatible_unit": return `«${text("entered_unit", "без единицы") || "без единицы"}» нельзя использовать для характеристики «${label}». Ожидается единица «${unit || "без единицы"}» или совместимая единица того же типа.`;
    case "expected_numeric_value": return `Для «${label}» ожидается одно числовое значение${unit ? ` в ${unit}` : ""}.`;
    case "expected_text_value": return `Для «${label}» ожидается текстовое значение. Выберите другую характеристику для числового значения.`;
    case "specification_definition_conflict": return `Название или тип характеристики «${label}» не соответствует существующему определению. Укажите другое название.`;
    case "numeric_value_out_of_range": return `Значение «${label}» выходит за допустимый диапазон или точность хранения.`;
    default: return "Проверьте значение поля.";
  }
}

const ERROR_MESSAGES: Readonly<Record<string, string>> = {
  duplicate_alias: "Альтернативные имена повторяются без учёта регистра. Удалите повтор.",
  duplicate_tag: "Теги повторяются без учёта регистра. Удалите повтор.",
  alias_too_long: "Альтернативное имя должно содержать от 1 до 100 символов.",
  tag_too_long: "Тег должен содержать от 1 до 100 символов.",
  too_many_aliases: "Допустимо не более 20 альтернативных имён.",
  too_many_tags: "Допустимо не более 20 тегов.",
  invalid_slug: "Адрес страницы: латинские буквы, цифры и дефисы.",
  invalid_specification: "Проверьте название, значение и единицу характеристики.",
  component_media_not_found: "Не удалось привязать изображение: файл недоступен или принадлежит другой карточке.",
  component_images_invalid: "Не удалось привязать изображения: проверьте количество и повторы.",
  media_component_size_exceeded: "Не удалось привязать изображения: превышен объём файлов карточки.",
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
  import_dispatch_exhausted: "Импорт не удалось запустить. Его можно повторить.",
  import_processing_failed: "Не удалось обработать данные компонента.",
  media_attempts_exhausted: "Не удалось обработать файл после нескольких попыток.",
  media_dispatch_exhausted: "Обработку файла не удалось запустить. Её можно повторить.",
  media_storage_failed: "Не удалось прочитать или сохранить файл.",
  media_storage_transient: "Хранилище файлов временно недоступно.",
  media_validation_failed: "Файл не прошёл проверку.",
};

export function userErrorMessage(
  error: unknown,
  fallback = "Не удалось выполнить действие. Попробуйте снова.",
): string {
  if (!(error instanceof ApiError)) return fallback;
  if (validationIssues(error).length) return "Не удалось сохранить: исправьте выделенные поля.";
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
