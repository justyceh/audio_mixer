import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from api.schemas.project import (
    ClipCreate,
    ClipOut,
    ClipUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectSummary,
    ProjectUpdate,
    TrackCreate,
    TrackOut,
    TrackUpdate,
)
from api.services import project_service

router = APIRouter(prefix="/api", tags=["projects"], dependencies=[Depends(get_current_user)])


class ProjectList(BaseModel):
    items: list[ProjectSummary]
    total: int
    limit: int
    offset: int


# --- Projects ----------------------------------------------------------------
@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    return project_service.create_project(db, body)


@router.get("/projects", response_model=ProjectList)
def list_projects(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    items, total = project_service.list_projects(db, limit, offset)
    return ProjectList(items=items, total=total, limit=limit, offset=offset)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Full project: tracks (ordered) → clips (by timeline position) → media metadata."""
    return project_service.get_project_full(db, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: uuid.UUID, body: ProjectUpdate, db: Session = Depends(get_db)):
    return project_service.update_project(db, project_id, body)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a project with its tracks and clips (media assets are kept)."""
    project_service.delete_project(db, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Tracks ------------------------------------------------------------------
@router.post("/projects/{project_id}/tracks", response_model=TrackOut, status_code=status.HTTP_201_CREATED)
def create_track(project_id: uuid.UUID, body: TrackCreate, db: Session = Depends(get_db)):
    return project_service.create_track(db, project_id, body)


@router.get("/tracks/{track_id}", response_model=TrackOut)
def get_track(track_id: uuid.UUID, db: Session = Depends(get_db)):
    return project_service.get_track(db, track_id)


@router.patch("/tracks/{track_id}", response_model=TrackOut)
def update_track(track_id: uuid.UUID, body: TrackUpdate, db: Session = Depends(get_db)):
    return project_service.update_track(db, track_id, body)


@router.delete("/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_track(track_id: uuid.UUID, db: Session = Depends(get_db)):
    project_service.delete_track(db, track_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Clips -------------------------------------------------------------------
@router.post("/tracks/{track_id}/clips", response_model=ClipOut, status_code=status.HTTP_201_CREATED)
def create_clip(track_id: uuid.UUID, body: ClipCreate, db: Session = Depends(get_db)):
    """Place a media asset on a track. `source_end` defaults to the media duration."""
    return project_service.create_clip(db, track_id, body)


@router.get("/clips/{clip_id}", response_model=ClipOut)
def get_clip(clip_id: uuid.UUID, db: Session = Depends(get_db)):
    return project_service.get_clip(db, clip_id)


@router.patch("/clips/{clip_id}", response_model=ClipOut)
def update_clip(clip_id: uuid.UUID, body: ClipUpdate, db: Session = Depends(get_db)):
    return project_service.update_clip(db, clip_id, body)


@router.delete("/clips/{clip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clip(clip_id: uuid.UUID, db: Session = Depends(get_db)):
    project_service.delete_clip(db, clip_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
