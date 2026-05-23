from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models
from app.auth import get_current_admin
from app.schemas import PrevisionMetaOut, PrevisionMetaUpdate

router = APIRouter(prefix="/api/configuracion", tags=["configuracion"])


@router.get("/prevision-meta", response_model=List[PrevisionMetaOut])
def list_prevision_meta(db: Session = Depends(get_db), _=Depends(get_current_admin)):
    return db.query(models.PrevisionMeta).order_by(models.PrevisionMeta.codigo).all()


@router.put("/prevision-meta/{meta_id}", response_model=PrevisionMetaOut)
def update_prevision_meta(
    meta_id: int,
    data: PrevisionMetaUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    pm = db.query(models.PrevisionMeta).filter(models.PrevisionMeta.id == meta_id).first()
    if not pm:
        raise HTTPException(404, "Entrada de previsión no encontrada")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(pm, field, value)
    db.commit()
    db.refresh(pm)
    return pm
