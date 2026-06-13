import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Book, FolderRule, RootFolder
from ..services.paths import display_path, normalize_root_path

router = APIRouter()


class RootCreate(BaseModel):
    path: str


class RuleCreate(BaseModel):
    kind: str  # include | exclude
    subpath: str


def _root_payload(session: Session, root: RootFolder) -> dict:
    rules = session.exec(
        select(FolderRule).where(FolderRule.root_id == root.id)
    ).all()
    return {
        "id": root.id,
        "path": root.path,
        "display_path": display_path(root.path),
        "exists": os.path.isdir(root.path),
        "rules": [
            {"id": r.id, "kind": r.kind, "subpath": r.subpath} for r in rules
        ],
    }


@router.get("/roots")
def list_roots(session: Session = Depends(get_session)):
    roots = session.exec(select(RootFolder)).all()
    return [_root_payload(session, r) for r in roots]


@router.post("/roots", status_code=201)
def add_root(body: RootCreate, session: Session = Depends(get_session)):
    try:
        path = normalize_root_path(body.path)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    existing = session.exec(
        select(RootFolder).where(RootFolder.path == path)
    ).first()
    if existing:
        raise HTTPException(409, detail=f"Folder already added: {display_path(path)}")
    root = RootFolder(path=path)
    session.add(root)
    session.commit()
    session.refresh(root)
    return _root_payload(session, root)


@router.delete("/roots/{root_id}")
def remove_root(root_id: int, session: Session = Depends(get_session)):
    root = session.get(RootFolder, root_id)
    if not root:
        raise HTTPException(404, detail=f"Root folder #{root_id} not found.")
    # Cascade removes rules and books (books cascade progress/bookmarks).
    count = len(
        session.exec(select(Book).where(Book.root_id == root_id)).all()
    )
    session.delete(root)
    session.commit()
    return {"removed_books": count}


@router.post("/roots/{root_id}/rescan", status_code=202)
def rescan_root(root_id: int, session: Session = Depends(get_session)):
    from .. import db
    from ..services.sync import SyncAlreadyRunning, sync_manager

    root = session.get(RootFolder, root_id)
    if not root:
        raise HTTPException(404, detail=f"Root folder #{root_id} not found.")
    try:
        run_id = sync_manager.start(db.engine, only_root_id=root_id)
    except SyncAlreadyRunning:
        raise HTTPException(
            409, detail="A sync is already running. Wait for it to finish."
        )
    return {"run_id": run_id}


@router.post("/roots/{root_id}/rules", status_code=201)
def add_rule(
    root_id: int, body: RuleCreate, session: Session = Depends(get_session)
):
    if body.kind not in ("include", "exclude"):
        raise HTTPException(
            400, detail=f"Rule kind must be 'include' or 'exclude', got: {body.kind}"
        )
    root = session.get(RootFolder, root_id)
    if not root:
        raise HTTPException(404, detail=f"Root folder #{root_id} not found.")
    subpath = body.subpath.strip().strip("/\\")
    if not subpath:
        raise HTTPException(400, detail="Rule subpath cannot be empty.")
    rule = FolderRule(root_id=root_id, kind=body.kind, subpath=subpath)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return {"id": rule.id, "kind": rule.kind, "subpath": rule.subpath}


@router.delete("/rules/{rule_id}")
def remove_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(FolderRule, rule_id)
    if not rule:
        raise HTTPException(404, detail=f"Rule #{rule_id} not found.")
    session.delete(rule)
    session.commit()
    return {"ok": True}
