"""FastAPI application factory and resource lifecycle."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from arduino_component_kb.api.admin import router as admin_router
from arduino_component_kb.api.auth import router as auth_router
from arduino_component_kb.api.catalog import admin_router as catalog_admin_router
from arduino_component_kb.api.catalog import public_router as catalog_public_router
from arduino_component_kb.api.catalog import router as catalog_router
from arduino_component_kb.api.duplicates import router as duplicates_router
from arduino_component_kb.api.health import router as health_router
from arduino_component_kb.api.import_reviews import router as import_reviews_router
from arduino_component_kb.api.imports import router as imports_router
from arduino_component_kb.api.jobs import router as jobs_router
from arduino_component_kb.api.media import router as media_router
from arduino_component_kb.auth.passwords import PasswordManager
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database, DatabaseGateway
from arduino_component_kb.imports.queue import DramatiqImportQueue, ImportQueue
from arduino_component_kb.logging import RequestContextMiddleware, configure_logging
from arduino_component_kb.media.queue import DramatiqMediaQueue
from arduino_component_kb.media.service import MediaQueue
from arduino_component_kb.media.storage import MediaStorage, MinioStorage
from arduino_component_kb.security import BrowserSecurityMiddleware

logger = logging.getLogger("arduino_component_kb.lifecycle")


def create_app(
    settings: Settings | None = None,
    database: DatabaseGateway | None = None,
    media_storage: MediaStorage | None = None,
    media_queue: MediaQueue | None = None,
    import_queue: ImportQueue | None = None,
) -> FastAPI:
    """Create an isolated application with explicit dependencies."""
    resolved_settings = settings or Settings()
    resolved_database = database or Database(resolved_settings)
    resolved_media_storage = media_storage or MinioStorage(resolved_settings)
    resolved_media_queue = media_queue or DramatiqMediaQueue(resolved_settings)
    resolved_import_queue = import_queue or DramatiqImportQueue()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("application_started")
        try:
            yield
        finally:
            await resolved_database.dispose()
            logger.info("application_stopped")

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = resolved_database
    app.state.password_manager = PasswordManager()
    app.state.media_storage = resolved_media_storage
    app.state.media_queue = resolved_media_queue
    app.state.import_queue = resolved_import_queue
    app.add_middleware(BrowserSecurityMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(jobs_router)
    app.include_router(media_router)
    app.include_router(imports_router)
    app.include_router(import_reviews_router)
    app.include_router(catalog_router)
    app.include_router(catalog_admin_router)
    app.include_router(catalog_public_router)
    app.include_router(duplicates_router)

    return app
