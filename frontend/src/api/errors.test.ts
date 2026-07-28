import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import {
  isPermissionError,
  isRetryableError,
  processingFailureMessage,
  userErrorMessage,
} from "./errors";

describe("safe user errors", () => {
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
});
