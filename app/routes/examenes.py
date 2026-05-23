from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from app.database import get_db
from app import models
from app.auth import get_current_user
from app.schemas import ExamenOut, ExamenCreate, ExamenResultado, ArchivoOut, ArchivoCreate

router = APIRouter(tags=["examenes_archivos"])


@router.get("/api/pacientes/{paciente_id}/examenes", response_model=List[ExamenOut])
def get_examenes(paciente_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    return (db.query(models.Examen).filter(models.Examen.paciente_id == paciente_id)
            .order_by(models.Examen.fecha_solicitado.desc()).all())


@router.post("/api/pacientes/{paciente_id}/examenes", response_model=ExamenOut)
def crear_examen(paciente_id: int, data: ExamenCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    examen = models.Examen(paciente_id=paciente_id, tipo=data.tipo, nombre=data.nombre,
                            urgente=data.urgente, estado="pendiente")
    db.add(examen)
    db.commit()
    db.refresh(examen)
    db.add(models.Evento(paciente_id=paciente_id, tipo="nota",
        descripcion=f"Examen solicitado{' [URGENTE]' if data.urgente else ''}: {data.nombre} ({data.tipo})", usuario=current_user.username))
    db.commit()
    return examen


@router.put("/api/examenes/{examen_id}/resultado")
def registrar_resultado(examen_id: int, data: ExamenResultado, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    examen = db.query(models.Examen).filter(models.Examen.id == examen_id).first()
    if not examen:
        raise HTTPException(404, "Examen no encontrado")
    examen.resultado = data.resultado
    examen.estado = "completado"
    examen.fecha_resultado = datetime.now(timezone.utc)
    db.commit()
    db.add(models.Evento(paciente_id=examen.paciente_id, tipo="nota",
        descripcion=f"Resultado registrado: {examen.nombre}", usuario=current_user.username))
    db.commit()
    return {"message": "Resultado registrado"}


@router.delete("/api/examenes/{examen_id}")
def cancelar_examen(examen_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    examen = db.query(models.Examen).filter(models.Examen.id == examen_id).first()
    if not examen:
        raise HTTPException(404, "Examen no encontrado")
    examen.estado = "cancelado"
    db.commit()
    return {"message": "Examen cancelado"}


@router.get("/api/examenes")
def get_todos_examenes(estado: Optional[str] = None, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    query = db.query(models.Examen).join(models.Paciente, models.Examen.paciente_id == models.Paciente.id)
    if estado:
        query = query.filter(models.Examen.estado == estado)
    examenes = query.order_by(models.Examen.fecha_solicitado.desc()).all()
    result = []
    for ex in examenes:
        result.append({
            "id": ex.id,
            "tipo": ex.tipo,
            "nombre": ex.nombre,
            "estado": ex.estado,
            "urgente": ex.urgente,
            "resultado": ex.resultado,
            "fecha_solicitado": ex.fecha_solicitado.isoformat() if ex.fecha_solicitado else None,
            "fecha_resultado": ex.fecha_resultado.isoformat() if ex.fecha_resultado else None,
            "paciente_id": ex.paciente_id,
            "paciente_nombre": ex.paciente.nombre if ex.paciente else "—",
            "paciente_rut": ex.paciente.rut if ex.paciente else "—",
        })
    return {"total": len(result), "examenes": result}


@router.get("/api/pacientes/{paciente_id}/archivos", response_model=List[ArchivoOut])
def get_archivos(paciente_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    return (db.query(models.Archivo).filter(models.Archivo.paciente_id == paciente_id)
            .order_by(models.Archivo.fecha_subida.desc()).all())


@router.post("/api/pacientes/{paciente_id}/archivos", response_model=ArchivoOut)
def subir_archivo(paciente_id: int, data: ArchivoCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    archivo = models.Archivo(paciente_id=paciente_id, nombre=data.nombre, tipo=data.tipo,
                              descripcion=data.descripcion, datos_b64=data.datos_b64, mime_type=data.mime_type)
    db.add(archivo)
    db.commit()
    db.refresh(archivo)
    db.add(models.Evento(paciente_id=paciente_id, tipo="nota",
        descripcion=f"Archivo adjunto: {data.nombre} ({data.tipo})", usuario=current_user.username))
    db.commit()
    return archivo


@router.delete("/api/archivos/{archivo_id}")
def eliminar_archivo(archivo_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    archivo = db.query(models.Archivo).filter(models.Archivo.id == archivo_id).first()
    if not archivo:
        raise HTTPException(404, "Archivo no encontrado")
    db.delete(archivo)
    db.commit()
    return {"message": "Archivo eliminado"}
