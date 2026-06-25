from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .. import db
from ..db import get_session
from ..models import RootFolder, SyncError
from ..services.paths import relative_display
from ..services.sync import SyncAlreadyRunning, sync_manager

router = APIRouter()


def _root_paths(session: Session):
    return [r.path for r in session.exec(select(RootFolder)).all()]


@router.post("/sync", status_code=202)
def start_sync(root_id: Optional[int] = None):
    try:
        run_id = sync_manager.start(db.engine, only_root_id=root_id)
    except SyncAlreadyRunning:
        raise HTTPException(
            409, detail="A sync is already running. Wait for it to finish."
        )
    return {"run_id": run_id}


@router.post("/sync/stop")
def stop_sync():
    return {"stopping": sync_manager.stop()}


@router.get("/sync/status")
def sync_status(session: Session = Depends(get_session)):
    data = sync_manager.get_progress_dict()
    roots = _root_paths(session)
    # Sanitize absolute paths so the UI never shows /mnt/d/... machine paths.
    if data.get("current_folder"):
        data["current_folder"] = relative_display(data["current_folder"], roots)
    data["errors"] = [
        {"file_path": relative_display(e["file_path"], roots), "message": e["message"]}
        for e in data.get("errors", [])
    ]
    return data


@router.get("/sync/errors")
def sync_errors(run_id: int, session: Session = Depends(get_session)):
    roots = _root_paths(session)
    errors = session.exec(
        select(SyncError).where(SyncError.run_id == run_id)
    ).all()
    return [
        {
            "id": e.id,
            "file_path": relative_display(e.file_path, roots),
            "message": e.message,
        }
        for e in errors
    ]
