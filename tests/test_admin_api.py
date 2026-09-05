"""Administrator user-management request boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from arduino_component_kb.api.admin import (
    CreateAdministratorRequest,
    CreateEditorRequest,
    EditorGrantRequest,
    ResetPasswordRequest,
)


def test_temporary_editor_requests_do_not_accept_client_roles() -> None:
    future = datetime.now(UTC) + timedelta(days=7)

    with pytest.raises(ValidationError):
        CreateEditorRequest.model_validate(
            {
                "login": "temporary-editor",
                "display_name": "Временный редактор",
                "password": "temporary-password",
                "editor_expires_at": future,
                "roles": ["administrator"],
            }
        )

    with pytest.raises(ValidationError):
        EditorGrantRequest.model_validate(
            {
                "editor_expires_at": future,
                "role": "administrator",
            }
        )


@pytest.mark.parametrize("field", ["role", "roles", "permissions", "display_name"])
def test_administrator_creation_request_accepts_no_client_owned_authorization(
    field: str,
) -> None:
    payload: dict[str, object] = {
        "login": "second-admin",
        "password": "safe-admin-password",
        field: ["administrator"] if field.endswith("s") else "administrator",
    }
    with pytest.raises(ValidationError):
        CreateAdministratorRequest.model_validate(payload)


def test_password_reset_request_accepts_only_a_password() -> None:
    with pytest.raises(ValidationError):
        ResetPasswordRequest.model_validate(
            {"password": "safe-new-password", "roles": ["administrator"]}
        )
