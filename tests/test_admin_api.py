"""Administrator user-management request boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from arduino_component_kb.api.admin import CreateEditorRequest, EditorGrantRequest


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
