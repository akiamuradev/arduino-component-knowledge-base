import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import {
  isPermissionError,
  isRetryableError,
  processingFailureMessage,
  userErrorMessage,
  validationIssues,
  validationIssueMessage,
} from "./errors";

describe("safe user errors", () => {
  it("parses structured diagnostics defensively and localizes safe metadata", () => {
    const issue = { path: ["specifications", 7, "value_text"], code: "expected_numeric_value", meta: { label: "Тактовая частота", expected_unit: "МГц" } };
    const error = new ApiError(422, "validation_failed", { issues: [null, {}, { ...issue, path: ["specifications", -1] }, { ...issue, code: [] }, issue] });
    expect(validationIssues(error)).toEqual([issue]);
    expect(validationIssueMessage(issue)).toBe("Для «Тактовая частота» ожидается одно числовое значение в МГц.");
    expect(userErrorMessage(error)).toBe("Не удалось сохранить: исправьте выделенные поля.");
    expect(validationIssues(new ApiError(409, "catalog_conflict", { issues: [issue] }))).toEqual([]);
    expect(validationIssues(new ApiError(422, "validation_failed", { issues: {} }))).toEqual([]);
    expect(validationIssueMessage({ path: ["slug"], code: "future_code", meta: {} })).toBe("Проверьте значение поля.");
  });
  it("explains permissions without exposing a server code", () => {
    const error = new ApiError(403, "permission_denied");
    expect(userErrorMessage(error)).toBe("Это действие недоступно для вашей роли.");
    expect(isPermissionError(error)).toBe(true);
  });

  it("preserves the retry hint from the API", () => {
    const error = new ApiError(
      503,
      "service_unavailable",
      undefined,
      "Сервис временно недоступен. Попробуйте снова.",
      true,
    );
    expect(isRetryableError(error)).toBe(true);
    expect(userErrorMessage(error)).toBe("Сервис временно недоступен. Попробуйте снова.");
  });

  it("hides unknown processing codes", () => {
    expect(processingFailureMessage("internal_parser_trace")).toBe(
      "Не удалось завершить обработку.",
    );
  });

  it("explains exhausted delivery without exposing infrastructure", () => {
    expect(processingFailureMessage("import_dispatch_exhausted")).toBe(
      "Импорт не удалось запустить. Его можно повторить.",
    );
    expect(processingFailureMessage("media_dispatch_exhausted")).toBe(
      "Обработку файла не удалось запустить. Её можно повторить.",
    );
  });
});
