from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "database": "not_checked",
    }


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=None)
def ready(db: Session = Depends(get_db)) -> JSONResponse | dict[str, str]:
    try:
        db.execute(text("SET LOCAL statement_timeout = 2000"))
        db.execute(text("SELECT 1"))
    except Exception:
        db.rollback()
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "unavailable",
            },
        )

    return {
        "status": "ready",
        "database": "ok",
    }