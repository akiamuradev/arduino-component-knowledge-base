"""Safe, stable API error responses shared by every HTTP boundary."""

from __future__ import annotations

import logging
import re
from typing import Final

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

_ERROR_CODE_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{0,79}$")

_CODE_MESSAGES: Final[dict[str, str]] = {
    "authentication_rate_limited": "Слишком много попыток. Подождите и попробуйте снова.",
    "authentication_required": "Войдите, чтобы продолжить.",
    "catalog_conflict": "Данные уже изменились. Обновите страницу и повторите действие.",
    "component_not_found": "Карточка компонента не найдена.",
    "cross_origin_forbidden": "Запрос с этой страницы недоступен.",
    "csrf_token_missing": "Сессия устарела. Обновите страницу и повторите действие.",
    "csrf_validation_failed": "Сессия устарела. Обновите страницу и повторите действие.",
    "duplicate_candidate_not_found": "Запись для проверки не найдена.",
    "duplicate_candidate_resolved": "Эта запись уже обработана. Обновите страницу.",
    "import_enqueue_failed": "Обработка временно недоступна. Попробуйте снова.",
    "import_job_not_found": "Загрузка не найдена.",
    "import_not_cancellable": "Эту загрузку уже нельзя отменить.",
    "import_not_retryable": "Эту загрузку нельзя запустить повторно.",
    "invalid_credentials": "Неверный логин или пароль.",
    "job_not_found": "Задача не найдена.",
    "job_not_retryable": "Эту задачу нельзя запустить повторно.",
    "media_enqueue_failed": "Обработка файла временно недоступна. Попробуйте снова.",
    "media_not_found": "Файл не найден.",
    "permission_denied": "Это действие недоступно для вашей роли.",
    "revision_conflict": "Данные уже изменились. Обновите страницу и повторите действие.",
    "source_disabled": "Выбранный источник сейчас недоступен.",
}

_STATUS_MESSAGES: Final[dict[int, str]] = {
    400: "Проверьте запрос и повторите действие.",
    401: "Войдите, чтобы продолжить.",
    403: "Это действие недоступно для вашей роли.",
    404: "Запрашиваемые данные не найдены.",
    409: "Данные уже изменились. Обновите страницу и повторите действие.",
    422: "Проверьте заполнение полей.",
    429: "Слишком много запросов. Подождите и попробуйте снова.",
    500: "Не удалось выполнить запрос. Попробуйте снова.",
    502: "Сервис временно недоступен. Попробуйте снова.",
    503: "Сервис временно недоступен. Попробуйте снова.",
    504: "Сервис не ответил вовремя. Попробуйте снова.",
}

_RETRYABLE_STATUSES: Final = frozenset({429, 500, 502, 503, 504})


def normalize_error_code(value: object, status_code: int) -> str:
    """Return a bounded public code without leaking arbitrary exception text."""
    if isinstance(value, str) and _ERROR_CODE_PATTERN.fullmatch(value):
        return value
    if status_code == 422:
        return "validation_failed"
    if status_code == 404:
        return "not_found"
    if status_code == 401:
        return "authentication_required"
    if status_code == 403:
        return "permission_denied"
    if status_code == 409:
        return "state_conflict"
    if status_code == 429:
        return "rate_limited"
    if status_code >= 500:
        return "service_unavailable" if status_code != 500 else "internal_error"
    return "request_failed"


def public_error_payload(
    *,
    status_code: int,
    code: object,
    request_id: str | None,
) -> dict[str, dict[str, object]]:
    """Build the only user-facing API error envelope."""
    safe_code = normalize_error_code(code, status_code)
    message = _CODE_MESSAGES.get(
        safe_code,
        _STATUS_MESSAGES.get(status_code, "Не удалось выполнить запрос."),
    )
    return {
        "error": {
            "code": safe_code,
            "message": message,
            "retryable": status_code in _RETRYABLE_STATUSES,
            "request_id": request_id,
        }
    }


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def _exception_code(detail: object, status_code: int) -> str:
    if isinstance(detail, dict):
        return normalize_error_code(detail.get("code"), status_code)
    return normalize_error_code(None, status_code)


async def http_exception_handler(request: Request, error: Exception) -> JSONResponse:
    """Translate deliberate HTTP failures to the stable public contract."""
    if not isinstance(error, HTTPException):
        raise error
    code = _exception_code(error.detail, error.status_code)
    logging.getLogger("arduino_component_kb.http").warning(
        "api_request_rejected",
        extra={
            "error_type": type(error).__name__,
            "status_code": error.status_code,
            "failure_code": code,
        },
    )
    return JSONResponse(
        status_code=error.status_code,
        content=public_error_payload(
            status_code=error.status_code,
            code=code,
            request_id=_request_id(request),
        ),
        headers=error.headers,
    )


async def validation_exception_handler(request: Request, error: Exception) -> JSONResponse:
    """Hide validation internals while retaining their class in structured logs."""
    if not isinstance(error, RequestValidationError):
        raise error
    logging.getLogger("arduino_component_kb.http").warning(
        "api_request_rejected",
        extra={
            "error_type": type(error).__name__,
            "status_code": 422,
            "failure_code": "validation_failed",
        },
    )
    return JSONResponse(
        status_code=422,
        content=public_error_payload(
            status_code=422,
            code="validation_failed",
            request_id=_request_id(request),
        ),
    )
