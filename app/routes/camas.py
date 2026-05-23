from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone
from app.database import get_db
from app import models
from app.auth import get_current_user
from app.schemas import CamaOut, ReservarCamaData
from app.helpers import _paciente_to_out, _safe_days_since

router = APIRouter(prefix="/api/camas", tags=["camas"])


@router.get("", response_model=List[CamaOut])
def get_camas(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    camas = db.query(models.Cama).all()
    result = []
    for c in camas:
        paciente_out = None
        # Solo mostrar paciente si la cama está ocupada y el paciente está activo
        if c.estado in ("ocupada", "reservada") and c.paciente and c.paciente.estado not in ("alta", "traslado_externo"):
            p = c.paciente
            if p.fecha_hospitalizacion:
                p.dias_estadia = _safe_days_since(p.fecha_hospitalizacion, now)
            paciente_out = _paciente_to_out(p, c.numero)
        result.append(CamaOut(id=c.id, numero=c.numero, unidad=c.unidad,
                               estado=c.estado, paciente=paciente_out))
    return result


@router.put("/{numero}/reservar")
def reservar_cama(numero: str, data: ReservarCamaData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cama = db.query(models.Cama).filter(models.Cama.numero == numero).first()
    if not cama:
        raise HTTPException(404, "Cama no encontrada")
    if cama.estado not in ("libre", "reservada"):
        raise HTTPException(400, "Solo se pueden reservar camas libres")
    cama.estado = "reservada"
    if data.paciente_id:
        cama.paciente_id = data.paciente_id
        p = db.query(models.Paciente).filter(models.Paciente.id == data.paciente_id).first()
        if p:
            p.estado = "en_admision"
            db.add(models.Evento(
                paciente_id=p.id, tipo="reserva",
                descripcion=f"Cama {numero} reservada — paciente en cola de admisión directa",
                usuario=current_user.username,
            ))
    db.commit()
    return {"message": "Cama reservada"}


@router.put("/{numero}/libre")
def liberar_cama(numero: str, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    cama = db.query(models.Cama).filter(models.Cama.numero == numero).first()
    if not cama:
        raise HTTPException(404, "Cama no encontrada")
    cama.estado = "libre"
    cama.paciente_id = None  # Asegurar que no quede referencia al paciente anterior
    db.commit()
    return {"message": "Cama disponible"}
