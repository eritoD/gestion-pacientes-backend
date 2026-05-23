from datetime import datetime, timezone
from typing import Optional
from app import models
from app.schemas import PacienteOut
from app.config import TRIAGE_LABELS


def _sufijo_fonasa(prevision_principal: str) -> bool:
    return prevision_principal == "FONASA"


def _safe_days_since(dt_stored, now=None):
    """Días desde dt_stored hasta now. Maneja datetimes naive (sin TZ) y aware (UTC)."""
    if dt_stored is None:
        return 0
    if now is None:
        now = datetime.now(timezone.utc)
    if dt_stored.tzinfo is None:
        dt_stored = dt_stored.replace(tzinfo=timezone.utc)
    return (now - dt_stored).days


def _ensure_aware(dt):
    """Convierte datetime naive a aware (UTC). Retorna None si dt es None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _paciente_to_out(p: models.Paciente, cama_numero=None) -> PacienteOut:
    return PacienteOut(
        id=p.id, nombre=p.nombre, rut=p.rut, edad=p.edad, sexo=p.sexo,
        prevision_principal=p.prevision_principal,
        prevision_sub=p.prevision_sub,
        prevision_apellido=p.prevision_apellido,
        sufijo_fonasa=p.sufijo_fonasa or False,
        prevision=p.prevision,
        sintomas=p.sintomas,
        diagnostico=p.diagnostico,
        diagnostico_cie10=p.diagnostico_cie10,
        comorbilidades=p.comorbilidades or "",
        direccion=p.direccion,
        estado=p.estado, unidad=p.unidad, fecha_ingreso=p.fecha_ingreso,
        fecha_hospitalizacion=p.fecha_hospitalizacion, fecha_alta=p.fecha_alta,
        valor_cuenta_estimado=p.valor_cuenta_estimado, dias_estadia=p.dias_estadia,
        cama_numero=cama_numero,
        telefono=p.telefono, contacto_emergencia=p.contacto_emergencia,
        alergias=p.alergias, medicamentos_actuales=p.medicamentos_actuales,
        grupo_sanguineo=p.grupo_sanguineo, peso_kg=p.peso_kg, talla_cm=p.talla_cm,
        observaciones_clinicas=p.observaciones_clinicas,
        nivel_triage=p.nivel_triage,
        categoria_solicitada=p.categoria_solicitada,
        orden_hospitalizacion=p.orden_hospitalizacion or False,
        fecha_orden=p.fecha_orden,
        check_clinico=p.check_clinico or False,
        check_admin=p.check_admin or False,
        fecha_doble_check=p.fecha_doble_check,
        fecha_asignacion_cama=p.fecha_asignacion_cama,
        fecha_llegada_unidad=p.fecha_llegada_unidad,
        admision_completada=p.admision_completada or False,
        fecha_admision=p.fecha_admision,
        pagare_firmado=p.pagare_firmado or False,
        atencion_medica_completada=p.atencion_medica_completada or False,
        fecha_atencion_medica=p.fecha_atencion_medica,
        indicaciones_medicas=p.indicaciones_medicas,
        prescripciones=p.prescripciones,
        presion_arterial=p.presion_arterial,
        frecuencia_cardiaca=p.frecuencia_cardiaca,
        temperatura=p.temperatura,
        saturacion_o2=p.saturacion_o2,
        frecuencia_respiratoria=p.frecuencia_respiratoria,
        interconsulta_pendiente=p.interconsulta_pendiente or False,
        tipo_interconsultor=p.tipo_interconsultor,
        fecha_interconsulta=p.fecha_interconsulta,
        tipo_alta=p.tipo_alta,
        alta_probable=p.alta_probable or False,
        traslado_pendiente=p.traslado_pendiente or False,
        indicacion_traslado=p.indicacion_traslado,
        unidad_traslado_destino=p.unidad_traslado_destino,
    )


def _build_cola_item(p, now):
    horas = round((now - _ensure_aware(p.fecha_ingreso)).total_seconds() / 3600, 1)
    return {
        "id": p.id,
        "nombre": p.nombre,
        "rut": p.rut,
        "edad": p.edad,
        "sexo": p.sexo,
        # Previsión — presente para módulos admin, filtrado en frontend en módulos clínicos
        "prevision_principal": p.prevision_principal,
        "prevision_sub": p.prevision_sub,
        "prevision_apellido": p.prevision_apellido,
        "sufijo_fonasa": p.sufijo_fonasa or False,
        "prevision": p.prevision,
        # Clínico
        "sintomas": p.sintomas,
        "diagnostico": p.diagnostico,
        "diagnostico_cie10": p.diagnostico_cie10,
        "comorbilidades": p.comorbilidades,
        "nivel_triage": p.nivel_triage,
        "categoria_solicitada": p.categoria_solicitada,
        "orden_hospitalizacion": p.orden_hospitalizacion or False,
        "check_clinico": p.check_clinico or False,
        "check_admin": p.check_admin or False,
        "admision_completada": p.admision_completada or False,
        "atencion_medica_completada": p.atencion_medica_completada or False,
        "pagare_firmado": p.pagare_firmado or False,
        "horas_espera": horas,
        "critico": horas > 4 or (p.nivel_triage is not None and p.nivel_triage <= 1),
        "fecha_ingreso": p.fecha_ingreso.isoformat() if p.fecha_ingreso else None,
        # Signos vitales (módulo triage/clínico)
        "presion_arterial": p.presion_arterial,
        "frecuencia_cardiaca": p.frecuencia_cardiaca,
        "temperatura": p.temperatura,
        "saturacion_o2": p.saturacion_o2,
        "frecuencia_respiratoria": p.frecuencia_respiratoria,
        # Contacto (módulo admin)
        "telefono": p.telefono,
        "contacto_emergencia": p.contacto_emergencia,
        "indicaciones_medicas": p.indicaciones_medicas,
        "prescripciones": p.prescripciones,
        "observaciones_clinicas": p.observaciones_clinicas,
    }
