from fastapi import FastAPI

from apps.api.routes.health import router as health_router
from apps.api.routes.tenants import router as tenant_router
from apps.api.routes.data_sources import router as data_source_router
from apps.api.routes.documents import router as document_router
from apps.api.routes.search import router as search_router

def create_app() -> FastAPI:


    app = FastAPI(
        title="Enterprise Knowledge Intelligence Platform",
        version="0.1.0",
    )

    app.include_router(health_router)
    app.include_router(tenant_router)
    app.include_router(data_source_router)
    app.include_router(document_router)
    app.include_router(search_router)

    return app


app = create_app()