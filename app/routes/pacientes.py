from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime, timezone
from app.database import get_db
from app import models
from app.auth import get_current_user, get_current_admin
from app.schemas import (PacienteOut, PacienteCreate, HospitalizarData, DatosClinicosUpdate,
    TriageData, AdmisionData, AtencionMedicaData, OrdenHospitalizacionData, DobleCheckData,
    NotaCreate, AltaData, TrasladoInternoData, InterconsultaData, AtenderInterconsultaData)
from app.helpers import _paciente_to_out, _safe_days_since, _ensure_aware, _sufijo_fonasa
from app.config import TRIAGE_LABELS, TIPOS_ALTA_LABELS

router = APIRouter(prefix="/api/pacientes", tags=["pacientes"])


@router.get("/check-rut")
def check_rut(rut: str, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    ESTADOS_ACTIVOS = ("urgencias", "en_admision", "hospitalizado")
    p = db.query(models.Paciente).filter(
        models.Paciente.rut == rut,
        models.Paciente.estado.in_(ESTADOS_ACTIVOS)
    ).first()
    if p:
        return {"exists": True, "id": p.id, "nombre": p.nombre, "estado": p.estado, "activo": True}
    # Buscar también pacientes dados de alta (para info)
    p_alta = db.query(models.Paciente).filter(models.Paciente.rut == rut).first()
    if p_alta:
        return {"exists": True, "id": p_alta.id, "nombre": p_alta.nombre, "estado": p_alta.estado, "activo": False}
    return {"exists": False}


@router.get("", response_model=List[PacienteOut])
def get_pacientes(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    pacientes = db.query(models.Paciente).options(joinedload(models.Paciente.cama)).all()
    result = []
    _dirty = False
    for p in pacientes:
        if p.fecha_hospitalizacion and p.estado == "hospitalizado":
            new_dias = _safe_days_since(p.fecha_hospitalizacion, now)
            if p.dias_estadia != new_dias:
                p.dias_estadia = new_dias
                _dirty = True
        result.append(_paciente_to_out(p, p.cama.numero if p.cama else None))
    if _dirty:
        db.commit()
    return result


@router.post("", response_model=PacienteOut)
def crear_paciente(data: PacienteCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    existing = db.query(models.Paciente).filter(
        models.Paciente.rut == data.rut,
        models.Paciente.estado.in_(["urgencias", "en_admision", "hospitalizado"])
    ).first()
    if existing:
        raise HTTPException(400, f"Ya existe un paciente activo con ese RUT: {existing.nombre} (estado: {existing.estado})")
    p = models.Paciente(
        nombre=data.nombre, rut=data.rut, edad=data.edad, sexo=data.sexo,
        direccion=data.direccion,
        prevision_principal=data.prevision_principal,
        prevision_sub=data.prevision_sub,
        prevision_apellido=data.prevision_apellido,
        sufijo_fonasa=_sufijo_fonasa(data.prevision_principal),
        prevision=data.prevision_principal,
        comorbilidades=data.comorbilidades, estado="urgencias",
        fecha_ingreso=datetime.now(timezone.utc), dias_estadia=0,
        telefono=data.telefono,
        contacto_emergencia=data.contacto_emergencia,
        alergias=data.alergias,
        medicamentos_actuales=data.medicamentos_actuales,
        grupo_sanguineo=data.grupo_sanguineo,
        peso_kg=data.peso_kg,
        talla_cm=data.talla_cm,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    db.add(models.Evento(paciente_id=p.id, tipo="ingreso",
        descripcion=f"Ingreso administrativo — Previsión: {data.prevision_principal}", usuario=current_user.username))
    db.commit()
    return _paciente_to_out(p)


@router.get("/{paciente_id}", response_model=PacienteOut)
def get_paciente(paciente_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    cama = db.query(models.Cama).filter(models.Cama.paciente_id == p.id).first()
    if p.fecha_hospitalizacion and p.estado == "hospitalizado":
        new_dias = _safe_days_since(p.fecha_hospitalizacion)
        if p.dias_estadia != new_dias:
            p.dias_estadia = new_dias
            db.commit()
    return _paciente_to_out(p, cama.numero if cama else None)


@router.delete("/{paciente_id}")
def eliminar_paciente(paciente_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    cama = db.query(models.Cama).filter(models.Cama.paciente_id == p.id).first()
    if cama:
        cama.estado = "limpieza"  # Corregido: era "libre", debe pasar por limpieza
        cama.paciente_id = None
    db.delete(p)
    db.commit()
    return {"message": "Paciente eliminado del sistema"}


@router.post("/{paciente_id}/notas")
def add_nota(paciente_id: int, nota: NotaCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    db.add(models.Evento(paciente_id=paciente_id, tipo="nota", descripcion=nota.texto, usuario=current_user.username))
    db.commit()
    return {"message": "Nota registrada"}


@router.patch("/{paciente_id}/clinica")
def update_datos_clinicos(paciente_id: int, data: DatosClinicosUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(p, field, value)
    db.add(models.Evento(paciente_id=paciente_id, tipo="nota", descripcion="Datos clínicos actualizados", usuario=current_user.username))
    db.commit()
    return {"message": "Datos actualizados"}


@router.get("/{paciente_id}/eventos")
def get_eventos(paciente_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    eventos = (db.query(models.Evento).filter(models.Evento.paciente_id == paciente_id)
               .order_by(models.Evento.timestamp.desc()).all())
    return [{"tipo": e.tipo, "descripcion": e.descripcion, "timestamp": e.timestamp} for e in eventos]


@router.put("/{paciente_id}/triage")
def registrar_triage(paciente_id: int, data: TriageData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if data.nivel_triage not in range(6):
        raise HTTPException(400, "Nivel de triage debe ser 0-5")
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    p.nivel_triage = data.nivel_triage
    if data.sintomas:
        p.sintomas = data.sintomas
    if data.comorbilidades:
        p.comorbilidades = data.comorbilidades
    if data.presion_arterial:
        p.presion_arterial = data.presion_arterial
    if data.frecuencia_cardiaca:
        p.frecuencia_cardiaca = data.frecuencia_cardiaca
    if data.temperatura:
        p.temperatura = data.temperatura
    if data.saturacion_o2:
        p.saturacion_o2 = data.saturacion_o2
    if data.frecuencia_respiratoria:
        p.frecuencia_respiratoria = data.frecuencia_respiratoria
    db.add(models.Evento(
        paciente_id=paciente_id, tipo="triage",
        descripcion=f"Triage: {TRIAGE_LABELS.get(data.nivel_triage, f'Nivel {data.nivel_triage}')}",
        usuario=current_user.username,
    ))
    db.commit()
    return {"message": "Triage registrado"}


@router.put("/{paciente_id}/completar-admision")
def completar_admision(paciente_id: int, data: AdmisionData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")

    ingreso_directo = p.estado == "en_admision"
    now = datetime.now(timezone.utc)

    p.admision_completada = True
    p.fecha_admision = now
    p.pagare_firmado = data.pagare_firmado
    if data.telefono:
        p.telefono = data.telefono
    if data.contacto_emergencia:
        p.contacto_emergencia = data.contacto_emergencia
    if data.direccion:
        p.direccion = data.direccion
    if data.prevision_principal:
        p.prevision_principal = data.prevision_principal
        p.prevision = data.prevision_principal
        p.sufijo_fonasa = _sufijo_fonasa(data.prevision_principal)
    if data.prevision_sub:
        p.prevision_sub = data.prevision_sub
    if data.prevision_apellido:
        p.prevision_apellido = data.prevision_apellido

    db.add(models.Evento(
        paciente_id=paciente_id, tipo="admision",
        descripcion=f"Admisión completada — Pagaré {'firmado' if data.pagare_firmado else 'pendiente'}",
        usuario=current_user.username,
    ))

    if ingreso_directo and data.pagare_firmado:
        # Flujo directo: salta doble validación y va directamente a hospitalizado
        cama = db.query(models.Cama).filter(models.Cama.paciente_id == paciente_id).first()
        if cama:
            p.estado = "hospitalizado"
            p.unidad = cama.unidad
            p.fecha_hospitalizacion = now
            p.fecha_asignacion_cama = now
            p.check_clinico = True
            p.check_admin = True
            p.fecha_doble_check = now
            p.orden_hospitalizacion = True
            p.atencion_medica_completada = True
            cama.estado = "reservada"
            db.add(models.Evento(
                paciente_id=paciente_id, tipo="hospitalizacion",
                descripcion=f"Pagaré firmado — Paciente en tránsito a {cama.unidad} cama {cama.numero}",
            ))

    db.commit()
    return {"message": "Admisión completada", "ingreso_directo": ingreso_directo}


@router.put("/{paciente_id}/atencion-medica")
def registrar_atencion_medica(paciente_id: int, data: AtencionMedicaData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    p.atencion_medica_completada = True
    p.fecha_atencion_medica = datetime.now(timezone.utc)
    if data.observaciones_clinicas:
        p.observaciones_clinicas = data.observaciones_clinicas
    if data.indicaciones_medicas:
        p.indicaciones_medicas = data.indicaciones_medicas
    # Categoría sin sufijo F — la administración lo gestiona, no el médico
    p.orden_hospitalizacion = True
    p.categoria_solicitada = data.categoria_solicitada
    p.fecha_orden = datetime.now(timezone.utc)
    db.add(models.Evento(
        paciente_id=paciente_id, tipo="atencion_medica",
        descripcion=f"Atención médica completada — Orden emitida (Categoría: {data.categoria_solicitada})",
        usuario=current_user.username,
    ))
    db.commit()
    return {"message": "Atención médica registrada", "categoria": data.categoria_solicitada}


@router.put("/{paciente_id}/orden-hospitalizacion")
def emitir_orden(paciente_id: int, data: OrdenHospitalizacionData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    p.orden_hospitalizacion = True
    p.categoria_solicitada = data.categoria_solicitada
    p.fecha_orden = datetime.now(timezone.utc)
    db.add(models.Evento(
        paciente_id=paciente_id, tipo="orden",
        descripcion=f"Orden de hospitalización emitida — Categoría: {data.categoria_solicitada}",
        usuario=current_user.username,
    ))
    db.commit()
    return {"message": "Orden emitida", "categoria": data.categoria_solicitada}


@router.put("/{paciente_id}/doble-check")
def doble_check(paciente_id: int, data: DobleCheckData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    if not p.admision_completada:
        raise HTTPException(400, "La admisión no está completada")
    if not p.orden_hospitalizacion:
        raise HTTPException(400, "El paciente no tiene orden de hospitalización")
    p.check_clinico = data.check_clinico
    p.check_admin = data.check_admin
    if data.check_clinico and data.check_admin:
        p.fecha_doble_check = datetime.now(timezone.utc)
        db.add(models.Evento(paciente_id=paciente_id, tipo="doble_check",
            descripcion="Doble validación completada — Paciente listo para asignación de cama", usuario=current_user.username))
    else:
        db.add(models.Evento(paciente_id=paciente_id, tipo="nota",
            descripcion=f"Doble check — Clínico: {'✓' if data.check_clinico else '✗'} · Admin: {'✓' if data.check_admin else '✗'}", usuario=current_user.username))
    db.commit()
    return {"message": "Validación actualizada"}


@router.put("/{paciente_id}/paciente-llego")
def paciente_llego(paciente_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    now = datetime.now(timezone.utc)
    p.fecha_llegada_unidad = now
    transit_min = None
    if p.fecha_asignacion_cama:
        transit_min = round((now - _ensure_aware(p.fecha_asignacion_cama)).total_seconds() / 60, 1)
    # Marcar cama como ocupada al confirmar llegada
    cama = db.query(models.Cama).filter(models.Cama.paciente_id == paciente_id).first()
    if cama:
        cama.estado = "ocupada"
    desc = f"Paciente llegó a {p.unidad}"
    if transit_min is not None:
        desc += f" — Tránsito: {transit_min} min"
    db.add(models.Evento(paciente_id=paciente_id, tipo="llegada_unidad", descripcion=desc, usuario=current_user.username))
    db.commit()
    return {"message": "Llegada confirmada", "transit_min": transit_min}


@router.put("/{paciente_id}/hospitalizar")
def hospitalizar(paciente_id: int, data: HospitalizarData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    cama = db.query(models.Cama).filter(models.Cama.numero == data.nueva_cama_numero).first()
    if not cama:
        raise HTTPException(404, "Cama no encontrada")
    if cama.estado == "ocupada":
        raise HTTPException(400, "La cama ya está ocupada")
    if cama.estado == "limpieza":
        raise HTTPException(400, "La cama está en limpieza")
    if cama.estado == "reservada" and cama.paciente_id and cama.paciente_id != paciente_id:
        raise HTTPException(400, "La cama está reservada para otro paciente")
    # Liberar cama anterior si tiene una asignada (traslado)
    cama_anterior = db.query(models.Cama).filter(models.Cama.paciente_id == paciente_id).first()
    if cama_anterior and cama_anterior.numero != data.nueva_cama_numero:
        cama_anterior.estado = "limpieza"
        cama_anterior.paciente_id = None
        p.fecha_llegada_unidad = None  # queda en tránsito hacia nueva cama
    now = datetime.now(timezone.utc)
    p.estado = "hospitalizado"
    p.unidad = data.nueva_unidad
    p.fecha_hospitalizacion = now
    p.fecha_asignacion_cama = now
    p.traslado_pendiente = False
    cama.estado = "reservada"
    cama.paciente_id = p.id
    db.add(models.Evento(paciente_id=p.id, tipo="hospitalizacion",
        descripcion=f"Cama asignada: {data.nueva_unidad} — {data.nueva_cama_numero}", usuario=current_user.username))
    db.commit()
    return {"message": "Paciente hospitalizado"}


@router.put("/{paciente_id}/alta")
def dar_alta(paciente_id: int, data: AltaData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    # Congelar días de estadía reales al momento del alta
    if p.fecha_hospitalizacion:
        p.dias_estadia = _safe_days_since(p.fecha_hospitalizacion)
    p.estado = "alta"
    p.fecha_alta = datetime.now(timezone.utc)
    p.tipo_alta = data.tipo_alta
    cama = db.query(models.Cama).filter(models.Cama.paciente_id == p.id).first()
    if cama:
        cama.estado = "limpieza"
        cama.paciente_id = None
    label = TIPOS_ALTA_LABELS.get(data.tipo_alta, data.tipo_alta)
    db.add(models.Evento(paciente_id=p.id, tipo="alta", descripcion=f"{label} otorgada", usuario=current_user.username))
    db.commit()
    return {"message": "Alta otorgada"}


@router.put("/{paciente_id}/alta-probable")
def toggle_alta_probable(paciente_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    p.alta_probable = not p.alta_probable
    desc = "Alta probable marcada — se desocupará mañana" if p.alta_probable else "Alta probable removida"
    db.add(models.Evento(paciente_id=p.id, tipo="nota", descripcion=desc, usuario=current_user.username))
    db.commit()
    return {"message": desc, "alta_probable": p.alta_probable}


@router.post("/{paciente_id}/traslado-interno")
def traslado_interno(paciente_id: int, data: TrasladoInternoData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    p.traslado_pendiente = True
    p.indicacion_traslado = data.indicacion_medica
    p.unidad_traslado_destino = data.unidad_destino
    db.add(models.Evento(
        paciente_id=p.id, tipo="traslado",
        descripcion=f"Orden de traslado a {data.unidad_destino} — Indicación: {data.indicacion_medica}",
        usuario=current_user.username,
    ))
    db.commit()
    return {"message": "Solicitud de traslado emitida"}


@router.post("/{paciente_id}/interconsulta")
def registrar_interconsulta(paciente_id: int, data: InterconsultaData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")

    # Liberar cama actual si existe
    cama = db.query(models.Cama).filter(models.Cama.paciente_id == p.id).first()
    if cama:
        cama.estado = "limpieza"
        cama.paciente_id = None

    # Registrar interconsulta y devolver al pipeline de asignación de cama
    p.interconsulta_pendiente = True
    p.tipo_interconsultor = data.tipo_interconsultor
    p.fecha_interconsulta = datetime.now(timezone.utc)
    p.estado = "urgencias"
    p.unidad = None
    p.fecha_hospitalizacion = None
    p.fecha_asignacion_cama = None
    p.fecha_llegada_unidad = None
    # Mantiene check_clinico y check_admin para que quede listo para cama inmediatamente
    p.check_clinico = True
    p.check_admin = True

    db.add(models.Evento(
        paciente_id=paciente_id, tipo="interconsulta",
        descripcion=f"Interconsulta solicitada — Derivado a: {data.tipo_interconsultor}",
        usuario=current_user.username,
    ))
    db.commit()
    return {"message": "Interconsulta registrada", "tipo_interconsultor": data.tipo_interconsultor}


@router.put("/{paciente_id}/atender-interconsulta")
def atender_interconsulta(paciente_id: int, data: AtenderInterconsultaData, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Paciente).filter(models.Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    p.interconsulta_pendiente = False
    if data.diagnostico_actualizado:
        p.diagnostico = data.diagnostico_actualizado
    nota_desc = data.nota if data.nota else f"Interconsulta con {p.tipo_interconsultor} atendida"
    db.add(models.Evento(paciente_id=paciente_id, tipo="nota",
        descripcion=f"Interconsulta atendida: {nota_desc}", usuario=current_user.username))
    db.commit()
    return {"message": "Interconsulta atendida"}
