"""Resource endpoints — content management by Veterinary Experts."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentAccountDep, CurrentVetDep, DbDep
from app.domain.exceptions import NotFoundException
from app.domain.media_storage import MediaStorage
from app.models.account import PetOwner
from app.models.resource import Resource, ResourceStatus
from app.schemas.common import ResourceIn, ResourceOut

router = APIRouter(prefix="/resources", tags=["resources"])

# Stateless — safe to share.
_media = MediaStorage()


@router.get("", response_model=list[ResourceOut])
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


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
async def create_resource(
    payload: ResourceIn, vet: CurrentVetDep, db: DbDep
) -> Resource:
    """Create a new resource in DRAFT status (SRS 7.3).

    MediaStorage validates the file format and size before we let the row
    hit the database; this enforces the boundary case in SRS 1.3.2 at the
    earliest possible point in the request lifecycle.
    """
    descriptor = _media.accept(
        content_type=payload.content_type,
        media_path=payload.media_path,
        size_bytes=payload.size_bytes,
    )
    resource = Resource(
        title=payload.title,
        content_type=descriptor.content_type,
        media_path=descriptor.media_path,
        pet_type_id=payload.pet_type_id,
        author_id=vet.id,
        status=ResourceStatus.DRAFT,
    )
    db.add(resource)
    await db.commit()
    await db.refresh(resource, attribute_names=["pet_type"])
    return resource


@router.post("/{resource_id}/publish", response_model=ResourceOut)
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
