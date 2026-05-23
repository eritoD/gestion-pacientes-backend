from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
from app.database import get_db
from app import models
from app.auth import get_current_user
from app.helpers import _ensure_aware, _safe_days_since

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    total    = db.query(models.Cama).count()
    ocupadas = db.query(models.Cama).filter(models.Cama.estado == "ocupada").count()
    libres   = db.query(models.Cama).filter(models.Cama.estado == "libre").count()
    limpieza = db.query(models.Cama).filter(models.Cama.estado == "limpieza").count()

    now = datetime.now(timezone.utc)
    pacientes_hosp = db.query(models.Paciente).filter(models.Paciente.estado == "hospitalizado").all()
    pacientes_urg  = db.query(models.Paciente).filter(models.Paciente.estado == "urgencias").all()

    por_prevision: dict = {}
    por_prevision_jerarquica: dict = {}
    total_facturacion = 0.0
    riesgo = []

    for p in pacientes_hosp:
        prev = p.prevision_principal or p.prevision or "Desconocido"
        por_prevision[prev] = por_prevision.get(prev, 0) + 1
        total_facturacion += p.valor_cuenta_estimado

        sub = p.prevision_sub or "—"
        key = f"{prev} — {sub}" if sub != "—" else prev
        por_prevision_jerarquica[key] = por_prevision_jerarquica.get(key, 0) + 1

        dias = _safe_days_since(p.fecha_hospitalizacion, now) if p.fecha_hospitalizacion else p.dias_estadia
        if dias >= 7:
            riesgo.append({
                "nombre": p.nombre, "prevision": prev,
                "unidad": p.unidad, "dias": dias, "valor": p.valor_cuenta_estimado,
            })

    camas_agg = db.query(
        models.Cama.unidad, models.Cama.estado, func.count(models.Cama.id)
    ).group_by(models.Cama.unidad, models.Cama.estado).all()
    _cama_counts: dict = {}
    for unidad, estado, cnt in camas_agg:
        _cama_counts.setdefault(unidad, {})[estado] = cnt
    por_unidad = {}
    for unidad, estados in _cama_counts.items():
        t = sum(estados.values())
        o = estados.get("ocupada", 0)
        if t > 0:
            por_unidad[unidad] = {"total": t, "ocupadas": o, "libres": t - o}

    return {
        "resumen_camas": {
            "total": total, "ocupadas": ocupadas, "libres": libres, "limpieza": limpieza,
            "ocupacion_pct": round(ocupadas / total * 100, 1) if total else 0,
        },
        "por_unidad": por_unidad,
        "por_prevision": [{"name": k, "value": v} for k, v in por_prevision.items()],
        "por_prevision_jerarquica": [{"name": k, "value": v} for k, v in por_prevision_jerarquica.items()],
        "financiero": {
            "total_facturacion_estimada": total_facturacion,
            "dinero_en_riesgo": sum(r["valor"] for r in riesgo),
            "pacientes_larga_data": riesgo,
        },
        "urgencias_en_espera": len(pacientes_urg),
    }


@router.get("/financiero")
def get_dashboard_financiero(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    pacientes = db.query(models.Paciente).filter(models.Paciente.estado == "hospitalizado").all()

    pm_records = db.query(models.PrevisionMeta).all()
    prevision_meta_db = {pm.codigo: pm for pm in pm_records}

    breakdown: dict = {}
    for p in pacientes:
        prev = p.prevision_principal or p.prevision or "Desconocido"
        if prev not in breakdown:
            pm = prevision_meta_db.get(prev)
            meta = {
                "label": pm.label if pm else prev,
                "tarifa_dia": pm.tarifa_dia if pm else 80_000,
                "riesgo": pm.riesgo if pm else "Desconocido",
                "cobertura": pm.cobertura if pm else "—",
                "color": pm.color if pm else "gray",
            }
            breakdown[prev] = {
                "prevision": prev, "label": meta["label"], "riesgo": meta["riesgo"],
                "cobertura": meta["cobertura"], "color": meta["color"],
                "count": 0, "dias_totales": 0, "facturacion_estimada": 0.0,
                "dinero_en_riesgo": 0.0, "pacientes_larga_data": [],
                "subcuentas": {},
            }

        dias = _safe_days_since(p.fecha_hospitalizacion, now) if p.fecha_hospitalizacion else p.dias_estadia
        breakdown[prev]["count"] += 1
        breakdown[prev]["dias_totales"] += dias
        breakdown[prev]["facturacion_estimada"] += p.valor_cuenta_estimado

        sub = p.prevision_sub or "—"
        breakdown[prev]["subcuentas"][sub] = breakdown[prev]["subcuentas"].get(sub, 0) + 1

        if dias >= 7:
            breakdown[prev]["dinero_en_riesgo"] += p.valor_cuenta_estimado
            breakdown[prev]["pacientes_larga_data"].append({
                "nombre": p.nombre, "dias": dias,
                "valor": p.valor_cuenta_estimado, "unidad": p.unidad,
            })

    for data in breakdown.values():
        data["dias_promedio"] = round(data["dias_totales"] / data["count"], 1) if data["count"] else 0

    total_facturacion = sum(d["facturacion_estimada"] for d in breakdown.values())
    total_riesgo = sum(d["dinero_en_riesgo"] for d in breakdown.values())

    chart_data = sorted(
        [{"name": d["prevision"], "Facturación": round(d["facturacion_estimada"]),
          "Riesgo": round(d["dinero_en_riesgo"])} for d in breakdown.values()],
        key=lambda x: -x["Facturación"],
    )

    return {
        "breakdown": list(breakdown.values()),
        "total_facturacion": total_facturacion,
        "total_riesgo": total_riesgo,
        "chart_data": chart_data,
    }


@router.get("/operaciones")
def get_dashboard_operaciones(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)

    urgencias = db.query(models.Paciente).filter(models.Paciente.estado == "urgencias").all()
    pipeline = []
    for p in urgencias:
        horas = round((now - _ensure_aware(p.fecha_ingreso)).total_seconds() / 3600, 1)
        pipeline.append({
            "id": p.id, "nombre": p.nombre,
            "prevision_principal": p.prevision_principal,
            "sintomas": p.sintomas, "comorbilidades": p.comorbilidades,
            "horas_espera": horas, "critico": horas > 4,
        })
    pipeline.sort(key=lambda x: -x["horas_espera"])

    hospitalizados = db.query(models.Paciente).filter(
        models.Paciente.estado == "hospitalizado",
        models.Paciente.fecha_hospitalizacion.isnot(None),
    ).all()

    tiempos = []
    for p in hospitalizados:
        if p.fecha_hospitalizacion and p.fecha_ingreso:
            delta = (p.fecha_hospitalizacion - p.fecha_ingreso).total_seconds() / 3600
            if 0 < delta < 72:
                tiempos.append(delta)

    avg_admision = round(sum(tiempos) / len(tiempos), 1) if tiempos else 0

    tiempos_por_unidad = {}
    for p in hospitalizados:
        if p.unidad and p.fecha_hospitalizacion and p.fecha_ingreso:
            delta = (p.fecha_hospitalizacion - p.fecha_ingreso).total_seconds() / 3600
            if 0 < delta < 72:
                tiempos_por_unidad.setdefault(p.unidad, []).append(delta)

    chart_tiempos = [
        {"unidad": u, "tiempo_promedio": round(sum(ts) / len(ts), 1)}
        for u, ts in tiempos_por_unidad.items() if ts
    ]

    tiempos_transito = []
    for p in hospitalizados:
        if p.fecha_asignacion_cama and p.fecha_llegada_unidad:
            mins = (p.fecha_llegada_unidad - p.fecha_asignacion_cama).total_seconds() / 60
            if 0 < mins < 120:
                tiempos_transito.append(mins)
    avg_transito = round(sum(tiempos_transito) / len(tiempos_transito), 1) if tiempos_transito else 0

    alertas = []
    for p in db.query(models.Paciente).filter(
        models.Paciente.estado == "hospitalizado", models.Paciente.unidad == "MQ"
    ).all():
        if p.dias_estadia >= 5:
            alertas.append({
                "nombre": p.nombre, "unidad": p.unidad, "dias": p.dias_estadia,
                "diagnostico": p.diagnostico_cie10 or p.diagnostico,
                "prevision": p.prevision_principal or p.prevision,
                "tipo": "escalada_potencial",
                "mensaje": f"Paciente con {p.dias_estadia} días en MQ — evaluar UCI/UTI",
            })

    for p in db.query(models.Paciente).filter(
        models.Paciente.estado == "hospitalizado", models.Paciente.dias_estadia >= 7,
    ).all():
        if p.unidad != "MQ":
            alertas.append({
                "nombre": p.nombre, "unidad": p.unidad, "dias": p.dias_estadia,
                "diagnostico": p.diagnostico_cie10 or p.diagnostico,
                "prevision": p.prevision_principal or p.prevision,
                "tipo": "larga_data",
                "mensaje": f"Paciente con {p.dias_estadia} días en {p.unidad} — revisar plan de alta",
            })

    alertas.sort(key=lambda x: -x["dias"])
    camas_limpieza = db.query(models.Cama).filter(models.Cama.estado == "limpieza").count()

    return {
        "pipeline_urgencias": pipeline,
        "total_en_espera": len(pipeline),
        "urgencias_criticas": sum(1 for p in pipeline if p["critico"]),
        "tiempo_promedio_admision_horas": avg_admision,
        "tiempo_promedio_transito_min": avg_transito,
        "camas_en_limpieza": camas_limpieza,
        "alertas_complejidad": alertas,
        "chart_tiempos": chart_tiempos,
        "meta": {
            "tiempo_ok": avg_admision <= 3,
            "sin_espera_critica": sum(1 for p in pipeline if p["critico"]) == 0,
        },
    }


@router.get("/eficiencia")
def get_dashboard_eficiencia(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    urgencias = db.query(models.Paciente).filter(models.Paciente.estado == "urgencias").all()

    ETAPAS_META = {
        "triage":         {"label": "Triage",             "meta_h": 0.5,  "umbral_critico_h": 1.0},
        "admision":       {"label": "Admisión",           "meta_h": 1.0,  "umbral_critico_h": 1.5},
        "atencion_medica":{"label": "Atención Médica",    "meta_h": 1.5,  "umbral_critico_h": 2.5},
        "doble_check":    {"label": "Doble Validación",   "meta_h": 0.5,  "umbral_critico_h": 1.0},
        "cama_pendiente": {"label": "Pendiente Cama",     "meta_h": 1.0,  "umbral_critico_h": 2.0},
    }

    etapa_esperas: dict = {k: [] for k in ETAPAS_META}
    etapa_counts: dict = {k: 0 for k in ETAPAS_META}

    for p in urgencias:
        if p.nivel_triage is None:
            etapa = "triage"
            t0 = p.fecha_ingreso
        elif not (p.admision_completada or False):
            etapa = "admision"
            t0 = p.fecha_ingreso
        elif not (p.atencion_medica_completada or False):
            etapa = "atencion_medica"
            t0 = p.fecha_admision or p.fecha_ingreso
        elif not ((p.check_clinico or False) and (p.check_admin or False)):
            etapa = "doble_check"
            t0 = p.fecha_atencion_medica or p.fecha_admision or p.fecha_ingreso
        else:
            etapa = "cama_pendiente"
            t0 = p.fecha_doble_check or p.fecha_ingreso

        etapa_counts[etapa] += 1
        if t0 is not None:
            horas = (_ensure_aware(now) - _ensure_aware(t0)).total_seconds() / 3600
            etapa_esperas[etapa].append(max(0, round(horas, 2)))

    hospitalizados = db.query(models.Paciente).filter(
        models.Paciente.estado == "hospitalizado",
        models.Paciente.fecha_asignacion_cama.isnot(None),
        models.Paciente.fecha_llegada_unidad.isnot(None),
    ).all()
    transitos = []
    for p in hospitalizados:
        mins = (_ensure_aware(p.fecha_llegada_unidad) - _ensure_aware(p.fecha_asignacion_cama)).total_seconds() / 60
        if 0 < mins < 120:
            transitos.append(round(mins, 1))

    hoy_inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)
    altas_hoy = db.query(models.Paciente).filter(
        models.Paciente.estado == "hospitalizado",
        models.Paciente.fecha_hospitalizacion >= hoy_inicio,
    ).count()

    etapas_result = []
    for k, meta in ETAPAS_META.items():
        esperas = etapa_esperas[k]
        avg = round(sum(esperas) / len(esperas), 2) if esperas else 0
        criticos = sum(1 for h in esperas if h > meta["umbral_critico_h"])
        en_meta = sum(1 for h in esperas if h <= meta["meta_h"])
        pct_en_meta = round(en_meta / len(esperas) * 100) if esperas else 100
        etapas_result.append({
            "id": k,
            "label": meta["label"],
            "count": etapa_counts[k],
            "avg_horas": avg,
            "max_horas": round(max(esperas), 2) if esperas else 0,
            "criticos": criticos,
            "meta_horas": meta["meta_h"],
            "umbral_critico": meta["umbral_critico_h"],
            "pct_en_meta": pct_en_meta,
        })

    bottleneck = max(etapas_result, key=lambda e: e["avg_horas"] - e["meta_horas"], default=None)

    altas_probables = db.query(models.Paciente).filter(
        models.Paciente.alta_probable == True,
        models.Paciente.estado == "hospitalizado",
    ).count()

    altas_entregadas_hoy = db.query(models.Paciente).filter(
        models.Paciente.estado == "alta",
        models.Paciente.fecha_alta.isnot(None),
        models.Paciente.fecha_alta >= hoy_inicio,
    ).count()

    interconsultas_q = db.query(models.Paciente).filter(
        models.Paciente.tipo_interconsultor.isnot(None),
    ).all()

    ic_pendientes = sum(1 for p in interconsultas_q if p.interconsulta_pendiente)
    ic_realizadas = sum(1 for p in interconsultas_q if not p.interconsulta_pendiente)

    ic_por_tipo: dict = {}
    for p in interconsultas_q:
        t = p.tipo_interconsultor or "Otro"
        if t not in ic_por_tipo:
            ic_por_tipo[t] = {"tipo": t, "pendiente": 0, "realizada": 0}
        if p.interconsulta_pendiente:
            ic_por_tipo[t]["pendiente"] += 1
        else:
            ic_por_tipo[t]["realizada"] += 1

    return {
        "etapas": etapas_result,
        "total_en_pipeline": len(urgencias),
        "bottleneck_id": bottleneck["id"] if bottleneck and bottleneck["avg_horas"] > bottleneck["meta_horas"] else None,
        "avg_transito_min": round(sum(transitos) / len(transitos), 1) if transitos else 0,
        "altas_hoy": altas_hoy,
        "total_etapas_ok": sum(1 for e in etapas_result if e["pct_en_meta"] >= 80),
        "altas_probables": altas_probables,
        "altas_entregadas_hoy": altas_entregadas_hoy,
        "pct_conversion_altas": round(altas_entregadas_hoy / altas_probables * 100) if altas_probables > 0 else 0,
        "interconsultas_cargadas": len(interconsultas_q),
        "interconsultas_pendientes": ic_pendientes,
        "interconsultas_realizadas": ic_realizadas,
        "interconsultas_desglose": list(ic_por_tipo.values()),
    }


@router.get("/gestion-pacientes")
def get_dashboard_gestion_pacientes(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    hoy_inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_7am  = hoy_inicio.replace(hour=7)

    total_camas = db.query(models.Cama).count()
    hosp_all = db.query(models.Paciente).filter(
        models.Paciente.fecha_hospitalizacion.isnot(None),
    ).all()

    ocupadas_7am = sum(
        1 for p in hosp_all
        if _ensure_aware(p.fecha_hospitalizacion) <= _ensure_aware(today_7am)
        and (p.fecha_alta is None or _ensure_aware(p.fecha_alta) >= _ensure_aware(today_7am))
    )
    pct_7am = round(ocupadas_7am / total_camas * 100, 1) if total_camas else 0

    ocupadas_ahora = db.query(models.Cama).filter(models.Cama.estado == "ocupada").count()
    limpieza_ahora = db.query(models.Cama).filter(models.Cama.estado == "limpieza").count()
    libres_ahora   = max(0, total_camas - ocupadas_ahora - limpieza_ahora)

    camas_agg = db.query(
        models.Cama.unidad, models.Cama.estado, func.count(models.Cama.id)
    ).group_by(models.Cama.unidad, models.Cama.estado).all()
    _cama_counts: dict = {}
    for unidad, estado, cnt in camas_agg:
        _cama_counts.setdefault(unidad, {})[estado] = cnt
    UNIDADES = ["UCI", "UCO UTI", "UCO UI", "UTI", "MQ", "Recuperacion", "Urgencia"]
    desglose = []
    for unidad in UNIDADES:
        estados = _cama_counts.get(unidad, {})
        t = sum(estados.values())
        if t == 0:
            continue
        o = estados.get("ocupada", 0)
        l = estados.get("limpieza", 0)
        r = estados.get("reservada", 0)
        desglose.append({
            "unidad": unidad, "total": t, "ocupadas": o,
            "libres": max(0, t - o - l - r), "limpieza": l, "reservadas": r,
            "pct": round(o / t * 100, 1),
        })

    programados_q = db.query(models.Paciente).filter(
        models.Paciente.orden_hospitalizacion == True,
        models.Paciente.estado == "urgencias",
    ).all()

    lista_ingresos = []
    for p in programados_q:
        pendientes = []
        if not (p.admision_completada or False):
            pendientes.append("Admisión administrativa")
        if not (p.atencion_medica_completada or False):
            pendientes.append("Atención médica")
        if not ((p.check_clinico or False) and (p.check_admin or False)):
            pendientes.append("Doble validación")
        if not p.fecha_asignacion_cama:
            pendientes.append("Asignación de cama")
        lista_ingresos.append({
            "id": p.id, "nombre": p.nombre, "rut": p.rut,
            "categoria": p.categoria_solicitada or "—",
            "prevision": p.prevision_principal or p.prevision or "—",
            "pendientes": pendientes,
            "horas_espera": round((_ensure_aware(now) - _ensure_aware(p.fecha_ingreso)).total_seconds() / 3600, 1),
        })

    espera_cupo = sum(1 for p in programados_q if not p.fecha_asignacion_cama)

    salientes_hoy = db.query(models.Paciente).filter(
        models.Paciente.estado == "traslado_externo",
    ).count()

    entrantes_hoy = db.query(models.Paciente).filter(
        models.Paciente.estado == "hospitalizado",
        models.Paciente.fecha_hospitalizacion.isnot(None),
        models.Paciente.fecha_hospitalizacion >= hoy_inicio,
    ).count()

    asignaciones_hoy = db.query(models.Paciente).filter(
        models.Paciente.fecha_asignacion_cama.isnot(None),
        models.Paciente.fecha_asignacion_cama >= hoy_inicio,
    ).count()

    return {
        "snapshot_7am": {
            "total": total_camas, "ocupadas": ocupadas_7am,
            "libres": total_camas - ocupadas_7am, "pct": pct_7am, "hora": "07:00",
        },
        "ocupacion_actual": {
            "total": total_camas, "ocupadas": ocupadas_ahora,
            "libres": libres_ahora, "limpieza": limpieza_ahora,
            "pct": round(ocupadas_ahora / total_camas * 100, 1) if total_camas else 0,
        },
        "desglose_unidades": desglose,
        "ingresos_programados": lista_ingresos,
        "total_ingresos": len(lista_ingresos),
        "espera_cupo": espera_cupo,
        "traslados": {"entrantes_hoy": entrantes_hoy, "salientes_hoy": salientes_hoy},
        "asignaciones_hoy": asignaciones_hoy,
    }
