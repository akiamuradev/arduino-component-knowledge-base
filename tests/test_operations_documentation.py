"""Static contracts for the ACKB 1.0.0 operator guide."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "docs" / "OPERATIONS.md"


def read_operations() -> str:
    return OPERATIONS.read_text(encoding="utf-8")


def test_operator_guide_covers_every_release_stage_scenario() -> None:
    guide = read_operations()
    expected_sections = (
        "## 1. Установка на чистом сервере",
        "## 2. Настройка переменных окружения",
        "## 3. Запуск миграций",
        "## 4. Создание первого администратора",
        "## 5. Запуск приложения",
        "## 6. Проверка работоспособности",
        "## 7. Резервное копирование",
        "## 8. Восстановление",
        "## 9. Обновление с предыдущей версии",
        "## 10. Управление временными редакторами",
        "## 11. Просмотр журнала",
        "## 12. Действия при ошибке обработки компонентов",
        "## 13. Откат выпуска",
    )
    positions = [guide.index(section) for section in expected_sections]
    assert positions == sorted(positions)


def test_operator_commands_match_repository_interfaces() -> None:
    guide = read_operations()
    compose = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("compose.yaml", "compose.production.yaml")
    )
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    required_tokens = (
        ".env.production.example",
        "./scripts/production_preflight.sh",
        "alembic current",
        "20260729_27 (head)",
        "ackb-bootstrap-admin",
        "python3 scripts/production_smoke.py",
        "./scripts/database_backup.sh",
        "./scripts/database_restore.sh",
        "ackb_restore_incident",
        "ackb-reconcile-jobs",
        "git checkout --detach",
        "20260721_16",
    )
    for token in required_tokens:
        assert token in guide
    for service in (
        "postgres",
        "redis",
        "minio",
        "migrate",
        "database-permissions",
        "backend",
        "worker",
        "parser-worker",
        "job-reconciler",
        "frontend",
        "reverse-proxy",
    ):
        assert f"  {service}:" in compose
    for command in ("ackb-bootstrap-admin", "ackb-reconcile-jobs"):
        assert command in project
    for script in (
        "production_preflight.sh",
        "production_smoke.py",
        "database_backup.sh",
        "database_restore.sh",
    ):
        assert (ROOT / "scripts" / script).is_file()

    template = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    environment_keys = {
        line.partition("=")[0] for line in template.splitlines() if line.startswith("ACKB_")
    }
    documented_keys = set(re.findall(r"\bACKB_[A-Z0-9_]+\b", guide))
    assert environment_keys <= documented_keys


def test_operator_guide_covers_cross_store_recovery_and_safe_boundaries() -> None:
    guide = read_operations()
    for token in (
        "PostgreSQL dump",
        "minio-data",
        "sha256sum",
        "off-host storage",
        "production database не изменяет",
        "Не используйте `down --volumes`",
        "Не используйте `git reset --hard`",
        "string match -rq '^/var/lib/docker/volumes/[^/]+/_data$' $minio_mount; or exit 1",
    ):
        assert token in guide
    assert "admin/admin" not in guide
    assert "--password" not in guide


def test_operator_ui_paths_are_real_and_role_scoped() -> None:
    guide = read_operations()
    routes = (ROOT / "frontend" / "src" / "app" / "routes.tsx").read_text(encoding="utf-8")
    navigation = (ROOT / "frontend" / "src" / "app" / "navigation.ts").read_text(encoding="utf-8")
    assert "/admin/users" in guide
    assert "/admin/audit" in guide
    assert "/admin/jobs" in guide
    assert "/admin/import" in guide
    for path in ("users", "audit", "jobs", "import"):
        assert f'path: "{path}"' in routes
        assert f'path: "/admin/{path}"' in navigation
    assert "Операция доступна только administrator" in guide
    assert "Administrator открывает `/admin/audit`" in guide
    assert "Редактор видит собственные загрузки" in guide


def test_operator_guide_is_linked_and_packaged() -> None:
    readmes = [(ROOT / path).read_text(encoding="utf-8") for path in ("README.md", "README.ru.md")]
    deployment = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert all(readme.count("(docs/OPERATIONS.md)") >= 1 for readme in readmes)
    assert "[`OPERATIONS.md`](OPERATIONS.md)" in deployment
    assert "recursive-include docs *.md" in manifest
    assert '"docs/*.md"' in project
