from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routes.health import router as health_router
from apps.api.routes.tenants import router as tenant_router
from apps.api.routes.data_sources import router as data_source_router
from apps.api.routes.documents import router as document_router
from apps.api.routes.search import router as search_router
from apps.api.routes.lexical_search import (
    router as lexical_search_router,
)
from apps.api.routes.query import router as query_router
from apps.api.routes.user import router as user_router

def create_app() -> FastAPI:


    app = FastAPI(
        title="Enterprise Knowledge Intelligence Platform",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(tenant_router)
    app.include_router(data_source_router)
    app.include_router(document_router)
    app.include_router(search_router)
    app.include_router(lexical_search_router)
    app.include_router(query_router)
    app.include_router(user_router)

    
    return app


app = create_app()