from fastapi import FastAPI

from apps.api.routes.health import router as health_router
from apps.api.routes.tenants import router as tenant_router

def create_app() -> FastAPI:


    app = FastAPI(
        title="Enterprise Knowledge Intelligence Platform",
        version="0.1.0",
    )

    app.include_router(health_router)
    app.include_router(tenant_router)

    return app


app = create_app()