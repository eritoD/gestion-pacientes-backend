from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone
from app.database import get_db
from app import models
from app.auth import get_current_user
from app.helpers import _build_cola_item, _ensure_aware, _paciente_to_out

router = APIRouter(prefix="/api/urgencias", tags=["urgencias"])


@router.get("/cola-triage")
def get_cola_triage(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    pacientes = db.query(models.Paciente).filter(
        models.Paciente.estado == "urgencias",
        models.Paciente.nivel_triage == None,
    ).all()
    items = [_build_cola_item(p, now) for p in pacientes]
    items.sort(key=lambda x: -x["horas_espera"])
    return {"pacientes": items, "total": len(items)}


@router.get("/cola-admision")
def get_cola_admision(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    # Pacientes urgencias con triage completado
    urgencias = db.query(models.Paciente).filter(
        models.Paciente.estado == "urgencias",
        models.Paciente.nivel_triage != None,
        models.Paciente.admision_completada == False,
    ).all()
    # Pacientes con cama reservada directamente (ingreso directo)
    directos = db.query(models.Paciente).filter(
        models.Paciente.estado == "en_admision",
        models.Paciente.admision_completada == False,
    ).all()
    items = []
    for p in urgencias:
        item = _build_cola_item(p, now)
        item["ingreso_directo"] = False
        items.append(item)
    for p in directos:
        item = _build_cola_item(p, now)
        item["ingreso_directo"] = True
        items.append(item)
    items.sort(key=lambda x: -x["horas_espera"])
    return {"pacientes": items, "total": len(items)}


@router.get("/cola-medica")
def get_cola_medica(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    pacientes = db.query(models.Paciente).filter(
        models.Paciente.estado == "urgencias",
        models.Paciente.admision_completada == True,
        models.Paciente.atencion_medica_completada == False,
    ).all()
    items = [_build_cola_item(p, now) for p in pacientes]
    items.sort(key=lambda x: -x["horas_espera"])
    return {"pacientes": items, "total": len(items)}


@router.get("/cola-doble-check")
def get_cola_doble_check(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    pacientes = db.query(models.Paciente).filter(
        models.Paciente.estado == "urgencias",
        models.Paciente.orden_hospitalizacion == True,
        models.Paciente.check_clinico == False,
    ).all()
    pacientes2 = db.query(models.Paciente).filter(
        models.Paciente.estado == "urgencias",
        models.Paciente.orden_hospitalizacion == True,
        models.Paciente.check_admin == False,
    ).all()
    seen = set()
    all_p = []
    for p in pacientes + pacientes2:
        if p.id not in seen:
            seen.add(p.id)
            all_p.append(p)
    items = [_build_cola_item(p, now) for p in all_p]
    items.sort(key=lambda x: -x["horas_espera"])
    return {"pacientes": items, "total": len(items)}


@router.get("/solicitudes-cama")
def get_solicitudes_cama(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    _with_cama = joinedload(models.Paciente.cama)
    listos = db.query(models.Paciente).filter(
        models.Paciente.estado == "urgencias",
        models.Paciente.check_clinico == True,
        models.Paciente.check_admin == True,
    ).all()
    en_transito = db.query(models.Paciente).options(_with_cama).filter(
        models.Paciente.estado == "hospitalizado",
        models.Paciente.fecha_llegada_unidad == None,
        models.Paciente.fecha_asignacion_cama != None,
    ).all()

    traslados = db.query(models.Paciente).options(_with_cama).filter(
        models.Paciente.estado == "hospitalizado",
        models.Paciente.traslado_pendiente == True,
    ).all()

    items_listos = [_build_cola_item(p, now) for p in listos]
    items_transito = []
    for p in en_transito:
        item = _build_cola_item(p, now)
        item["transit_min"] = round((now - _ensure_aware(p.fecha_asignacion_cama)).total_seconds() / 60, 1) if p.fecha_asignacion_cama else None
        item["unidad"] = p.unidad
        item["cama_numero"] = p.cama.numero if p.cama else None
        items_transito.append(item)

    items_traslado = []
    for p in traslados:
        item = _build_cola_item(p, now)
        item["unidad"] = p.unidad
        item["unidad_traslado_destino"] = p.unidad_traslado_destino
        item["indicacion_traslado"] = p.indicacion_traslado
        item["cama_numero"] = p.cama.numero if p.cama else None
        items_traslado.append(item)

    items_listos.sort(key=lambda x: -x["horas_espera"])
    items_transito.sort(key=lambda x: -(x.get("transit_min") or 0))
    return {
        "pendientes": items_listos, "en_transito": items_transito,
        "traslados": items_traslado,
        "total_pendientes": len(items_listos), "total_transito": len(items_transito),
        "total_traslados": len(items_traslado),
    }


@router.get("/pipeline")
def get_pipeline(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    urgencias = db.query(models.Paciente).filter(models.Paciente.estado == "urgencias").all()
    en_transito = db.query(models.Paciente).filter(
        models.Paciente.estado == "hospitalizado",
        models.Paciente.fecha_llegada_unidad == None,
        models.Paciente.fecha_asignacion_cama != None,
    ).all()

    def build_card(p, etapa):
        horas = round((now - _ensure_aware(p.fecha_ingreso)).total_seconds() / 3600, 1)
        transit_min = round((now - _ensure_aware(p.fecha_asignacion_cama)).total_seconds() / 60, 1) if p.fecha_asignacion_cama else None
        return {
            "id": p.id, "nombre": p.nombre, "rut": p.rut, "edad": p.edad,
            "sexo": p.sexo, "prevision_principal": p.prevision_principal,
            "sintomas": p.sintomas, "comorbilidades": p.comorbilidades,
            "nivel_triage": p.nivel_triage, "categoria_solicitada": p.categoria_solicitada,
            "orden_hospitalizacion": p.orden_hospitalizacion or False,
            "check_clinico": p.check_clinico or False, "check_admin": p.check_admin or False,
            "horas_espera": horas, "transit_min": transit_min,
            "critico": horas > 4 or (p.nivel_triage is not None and p.nivel_triage <= 1),
            "etapa": etapa, "unidad": p.unidad,
        }

    stages = {"triage": [], "admision": [], "atencion_medica": [], "doble_check": [], "cama_pendiente": [], "en_transito": []}

    for p in urgencias:
        if p.nivel_triage is None:
            etapa = "triage"
        elif not (p.admision_completada or False):
            etapa = "admision"
        elif not (p.atencion_medica_completada or False):
            etapa = "atencion_medica"
        elif not ((p.check_clinico or False) and (p.check_admin or False)):
            etapa = "doble_check"
        else:
            etapa = "cama_pendiente"
        stages[etapa].append(build_card(p, etapa))

    for p in en_transito:
        stages["en_transito"].append(build_card(p, "en_transito"))

    for s in stages.values():
        s.sort(key=lambda x: -x["horas_espera"])

    total = sum(len(s) for s in stages.values())
    criticos = sum(1 for s in stages.values() for p in s if p["critico"])
    all_p = [p for s in stages.values() for p in s]
    avg_espera = round(sum(p["horas_espera"] for p in all_p) / len(all_p), 1) if all_p else 0

    return {"stages": stages, "total": total, "criticos": criticos, "avg_espera": avg_espera}


@router.get("/cola-interconsulta")
def get_cola_interconsulta(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    pacientes = (db.query(models.Paciente)
                 .options(joinedload(models.Paciente.cama))
                 .filter(models.Paciente.interconsulta_pendiente == True)  # noqa: E712
                 .order_by(models.Paciente.fecha_interconsulta)
                 .all())
    result = [_paciente_to_out(p, p.cama.numero if p.cama else None) for p in pacientes]
    return {"total": len(result), "pacientes": result}
