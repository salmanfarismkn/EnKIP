
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from apps.api.schemas.user import (
    UserCreate,
    UserResponse,
    DataSourceAccessCreate,
    DataSourceAccessResponse,
)

# Replace these paths with your project's actual model paths.
from packages.domain.models import User
from packages.domain.models import Tenant
from packages.domain.models import DataSource
from packages.domain.models import DataSourceAccess


router = APIRouter(tags=["users and data-source access"])


@router.post(
    "/tenants/{tenant_id}/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    tenant_id: UUID,
    payload: UserCreate,
    db: Session = Depends(get_db),
):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    email = payload.email.strip().lower()

    existing_user = db.scalar(
        select(User).where(
            User.tenant_id == tenant_id,
            User.email == email,
        )
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=409,
            detail="A user with this email already exists in this tenant",
        )

    user = User(
        tenant_id=tenant_id,
        email=email,
        display_name=payload.display_name.strip(),
    )

    if not user.display_name:
        raise HTTPException(
            status_code=422,
            detail="display_name cannot be blank",
        )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not create user; the email may already exist",
        )

    return user


@router.delete(
    "/tenants/{tenant_id}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user(
    tenant_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
        )
    )
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found in this tenant",
        )

    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tenants/{tenant_id}/data-sources/{data_source_id}/access",
    response_model=DataSourceAccessResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_data_source_access(
    tenant_id: UUID,
    data_source_id: UUID,
    payload: DataSourceAccessCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(
            User.id == payload.user_id,
            User.tenant_id == tenant_id,
        )
    )
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found in this tenant",
        )

    data_source = db.scalar(
        select(DataSource).where(
            DataSource.id == data_source_id,
            DataSource.tenant_id == tenant_id,
        )
    )
    if data_source is None:
        raise HTTPException(
            status_code=404,
            detail="Data source not found in this tenant",
        )

    existing_access = db.scalar(
        select(DataSourceAccess).where(
            DataSourceAccess.tenant_id == tenant_id,
            DataSourceAccess.user_id == payload.user_id,
            DataSourceAccess.data_source_id == data_source_id,
        )
    )
    if existing_access is not None:
        response.status_code = status.HTTP_200_OK
        return existing_access

    access = DataSourceAccess(
        tenant_id=tenant_id,
        user_id=payload.user_id,
        data_source_id=data_source_id,
    )

    db.add(access)

    try:
        db.commit()
        db.refresh(access)
    except IntegrityError:
        # Another request may have granted access concurrently.
        db.rollback()

        existing_access = db.scalar(
            select(DataSourceAccess).where(
                DataSourceAccess.tenant_id == tenant_id,
                DataSourceAccess.user_id == payload.user_id,
                DataSourceAccess.data_source_id == data_source_id,
            )
        )
        if existing_access is not None:
            response.status_code = status.HTTP_200_OK
            return existing_access

        raise HTTPException(
            status_code=409,
            detail="Could not grant data-source access",
        )

    return access


@router.delete(
    "/tenants/{tenant_id}/data-sources/{data_source_id}/access/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_data_source_access(
    tenant_id: UUID,
    data_source_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
):
    access = db.scalar(
        select(DataSourceAccess).where(
            DataSourceAccess.tenant_id == tenant_id,
            DataSourceAccess.data_source_id == data_source_id,
            DataSourceAccess.user_id == user_id,
        )
    )

    if access is None:
        raise HTTPException(
            status_code=404,
            detail="Data-source access grant not found",
        )

    db.delete(access)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/tenants/{tenant_id}/users/{user_id}/data-sources",
    response_model=list[dict],
)
def list_user_data_sources(
    tenant_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
        )
    )
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found in this tenant",
        )

    rows = db.execute(
        select(DataSource.id, DataSource.name, DataSource.source_type)
        .join(
            DataSourceAccess,
            DataSourceAccess.data_source_id == DataSource.id,
        )
        .where(
            DataSourceAccess.tenant_id == tenant_id,
            DataSourceAccess.user_id == user_id,
            DataSource.tenant_id == tenant_id,
        )
        .order_by(DataSource.name)
    ).all()

    return [
        {
            "id": row.id,
            "name": row.name,
            "source_type": row.source_type,
        }
        for row in rows
    ]