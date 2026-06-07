"""Resource endpoints — content management by Veterinary Experts."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentAccountDep, CurrentVetDep, DbDep, require
from app.core.config import get_settings
from app.domain.exceptions import InvalidInputException, NotFoundException
from app.domain.permissions import Permission
from app.models.account import PetOwner
from app.models.resource import Resource, ResourceStatus
from app.schemas.common import ResourceIn, ResourceOut
from app.services.media_storage import r2_storage

router = APIRouter(prefix="/resources", tags=["resources"])

logger = logging.getLogger("petaid.resources")

_resource_manage = [Depends(require(Permission.RESOURCE_MANAGE))]


@router.get("", response_model=list[ResourceOut], dependencies=[Depends(require(Permission.RESOURCE_VIEW))])
async def list_resources(
    account: CurrentAccountDep,
    db: DbDep,
    pet_type_id: uuid.UUID | None = None,
) -> list[Resource]:
    """Pet Owners see only published resources; Vets see everything."""
    stmt = select(Resource).options(selectinload(Resource.pet_type))
    if isinstance(account, PetOwner):
        stmt = stmt.where(Resource.status == ResourceStatus.PUBLISHED)
    if pet_type_id is not None:
        stmt = stmt.where(Resource.pet_type_id == pet_type_id)
    rows = await db.scalars(stmt.order_by(Resource.created_at.desc()))
    return list(rows)


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED, dependencies=_resource_manage)
async def create_resource(
    payload: ResourceIn, vet: CurrentVetDep, db: DbDep
) -> Resource:
    """Create a new resource in DRAFT status (SRS 7.3).

    If ``media_key`` is supplied and R2 is configured, the backend calls
    ``head_object`` to confirm the browser finished its direct upload before
    we persist the row — preventing dangling references to non-existent objects.
    """
    if payload.media_key and get_settings().r2_enabled:
        try:
            await r2_storage.head_object(payload.media_key)
        except NotFoundException:
            raise InvalidInputException(
                "media_key",
                "Media not uploaded yet. Complete the direct upload to R2 first.",
            )

    resource = Resource(
        title=payload.title,
        content_type=payload.content_type,
        media_key=payload.media_key,
        pet_type_id=payload.pet_type_id,
        author_id=vet.id,
        status=ResourceStatus.DRAFT,
    )
    db.add(resource)
    await db.commit()
    await db.refresh(resource, attribute_names=["pet_type"])
    return resource


@router.post("/{resource_id}/publish", response_model=ResourceOut, dependencies=_resource_manage)
async def publish_resource(
    resource_id: uuid.UUID, vet: CurrentVetDep, db: DbDep
) -> Resource:
    resource = await db.get(Resource, resource_id)
    if resource is None:
        raise NotFoundException("Resource")
    resource.status = ResourceStatus.PUBLISHED
    await db.commit()
    await db.refresh(resource, attribute_names=["pet_type"])
    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_resource_manage)
async def delete_resource(
    resource_id: uuid.UUID, vet: CurrentVetDep, db: DbDep
) -> None:
    """Delete a resource and best-effort remove its backing R2 object (SRS 7.3).

    Vet-only (RESOURCE_MANAGE). Linked quizzes, feedback and first-aid links
    are removed by ``ON DELETE CASCADE`` at the database level. The DB row is
    deleted first; R2 object cleanup is best-effort afterwards so a failure to
    reach R2 can never leave a dangling database row (an orphaned object is
    harmless and can be swept later).
    """
    resource = await db.get(Resource, resource_id)
    if resource is None:
        raise NotFoundException("Resource")
    media_key = resource.media_key
    await db.delete(resource)
    await db.commit()
    if media_key and get_settings().r2_enabled:
        try:
            await r2_storage.delete_object(media_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "R2 delete_object failed for %s (%s) — row already removed",
                media_key,
                type(exc).__name__,
            )
