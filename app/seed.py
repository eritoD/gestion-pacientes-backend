from datetime import datetime, timedelta, timezone
import random
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models
from app.config import TRIAGE_LABELS
from app.auth import get_password_hash
from app.helpers import _sufijo_fonasa, _ensure_aware


# ── Datos inline (migrados desde config.py) ───────────────────────────────────

PREVISION_META_DATA = [
    {"codigo": "FONASA",       "label": "FONASA",                    "tarifa_dia": 48_000,  "riesgo": "Medio", "cobertura": "80% MLE",                "color": "blue"},
    {"codigo": "Isapre",       "label": "Isapre",                    "tarifa_dia": 115_000, "riesgo": "Bajo",  "cobertura": "90-100% Póliza",          "color": "purple"},
    {"codigo": "Particular",   "label": "Particular",                "tarifa_dia": 155_000, "riesgo": "Bajo",  "cobertura": "100% Pago directo",       "color": "gray"},
    {"codigo": "FF.AA.",       "label": "Fuerzas Armadas",           "tarifa_dia": 75_000,  "riesgo": "Bajo",  "cobertura": "Convenio institucional",  "color": "green"},
    {"codigo": "Ley Urgencia", "label": "FONASA — Ley de Urgencia",  "tarifa_dia": 75_000,  "riesgo": "Alto",  "cobertura": "FONASA MLE tope",        "color": "orange"},
    {"codigo": "GES",          "label": "FONASA — GES",              "tarifa_dia": 62_000,  "riesgo": "Medio", "cobertura": "Tarifa GES regulada",     "color": "teal"},
]

DEMO_USERS_DATA = [
    {"username": "admin",       "full_name": "Administrador",         "password": "admin",        "role": "admin"},
    {"username": "gestor",      "full_name": "Gestor de Pacientes",   "password": "gestor123",    "role": "gestor"},
    {"username": "jefatura",    "full_name": "Jefatura Clínica",      "password": "jefatura123",  "role": "jefatura"},
    {"username": "dr.martinez", "full_name": "Dr. Martínez García",   "password": "medico123",    "role": "medico"},
    {"username": "enf.gomez",   "full_name": "Enf. Gómez Vera",       "password": "enfermera123", "role": "enfermera"},
    {"username": "recepcion",   "full_name": "Recepción Central",     "password": "admin123",     "role": "administrativo"},
]

CAMAS_CONFIG_DATA = {
    "UCI":          [f"UCI-{i:02d}" for i in range(1, 7)],
    "UCO UTI":      [f"UCO-UTI-{i:02d}" for i in range(1, 5)],
    "UCO UI":       [f"UCO-UI-{i:02d}" for i in range(1, 7)],
    "UTI":          [f"UTI-{i:02d}" for i in range(1, 9)],
    "MQ":           [f"MQ-{i:02d}"  for i in range(1, 17)],
    "Recuperacion": [f"REC-{i:02d}" for i in range(1, 7)],
    "Urgencia":     [f"URG-{i:02d}" for i in range(1, 9)],
}

MOCK_PACIENTES_DATA = [
    # UCI
    {
        "nombre": "Andrés Muñoz Salinas",     "rut": "132456789", "edad": 64, "sexo": "M",
        "prevision_principal": "FONASA", "prevision_sub": "Libre Elección",
        "diagnostico": "Insuficiencia Cardíaca Aguda", "diagnostico_cie10": "I50.9",
        "sintomas": "Disnea ortopnea, edema bilateral miembros inferiores, crepitantes basales",
        "comorbilidades": "HTA, DM2, Cardiopatía", "unidad": "UCI", "cama": "UCI-01",
        "dias": 5, "horas_admision": 2.5,
    },
    {
        "nombre": "Beatriz Ramos Herrera",    "rut": "143567890", "edad": 58, "sexo": "F",
        "prevision_principal": "Isapre", "prevision_sub": "Cruz Blanca", "prevision_apellido": "Plan",
        "diagnostico": "Post-Op Cirugía Coronaria", "diagnostico_cie10": "Z48.0",
        "sintomas": "Vigilancia hemodinámica post-cirugía, dolor torácico residual",
        "comorbilidades": "Cardiopatía Isquémica, HTA", "unidad": "UCI", "cama": "UCI-02",
        "dias": 2, "horas_admision": 1.0,
    },
    {
        "nombre": "Cristóbal Vásquez León",   "rut": "154678901", "edad": 71, "sexo": "M",
        "prevision_principal": "FONASA", "prevision_sub": "GES",
        "diagnostico": "Neumonía Grave Bilateral", "diagnostico_cie10": "J18.1",
        "sintomas": "Disnea severa, fiebre persistente, requiere ventilación no invasiva",
        "comorbilidades": "EPOC, DM2", "unidad": "UCI", "cama": "UCI-03",
        "dias": 7, "horas_admision": 3.0,
    },
    # UCO UTI
    {
        "nombre": "Daniela Pizarro Mora",     "rut": "165789012", "edad": 52, "sexo": "F",
        "prevision_principal": "Isapre", "prevision_sub": "Banmédica", "prevision_apellido": "GES",
        "diagnostico": "SCA con Elevación ST", "diagnostico_cie10": "I21.0",
        "sintomas": "Dolor torácico opresivo, desnivel ST en ECG, biomarcadores elevados",
        "comorbilidades": "HTA, Tabaquismo", "unidad": "UCO UTI", "cama": "UCO-UTI-01",
        "dias": 3, "horas_admision": 1.5,
    },
    # UCO UI
    {
        "nombre": "Eduardo Neira Vargas",     "rut": "176890123", "edad": 67, "sexo": "M",
        "prevision_principal": "FONASA", "prevision_sub": "Ley Urgencia",
        "diagnostico": "Fibrilación Auricular con RVR", "diagnostico_cie10": "I48.0",
        "sintomas": "Palpitaciones irregulares, FC 130 bpm, inestabilidad hemodinámica leve",
        "comorbilidades": "HTA, Dislipidemia", "unidad": "UCO UI", "cama": "UCO-UI-01",
        "dias": 2, "horas_admision": 1.0,
    },
    # UTI
    {
        "nombre": "Francisca Gallardo Ríos",  "rut": "187901234", "edad": 34, "sexo": "F",
        "prevision_principal": "FONASA", "prevision_sub": "Libre Elección",
        "diagnostico": "TCE Moderado", "diagnostico_cie10": "S06.2",
        "sintomas": "Pérdida de conciencia, amnesia post-traumática, Glasgow 12",
        "comorbilidades": "Ninguna", "unidad": "UTI", "cama": "UTI-01",
        "dias": 4, "horas_admision": 2.0,
    },
    {
        "nombre": "Gabriel Espinoza Cid",     "rut": "198012345", "edad": 45, "sexo": "M",
        "prevision_principal": "Isapre", "prevision_sub": "Consalud", "prevision_apellido": "Plan",
        "diagnostico": "Shock Séptico", "diagnostico_cie10": "A41.9",
        "sintomas": "Fiebre >39°C, hipotensión refractaria, foco abdominal",
        "comorbilidades": "DM2", "unidad": "UTI", "cama": "UTI-02",
        "dias": 6, "horas_admision": 3.0,
    },
    {
        "nombre": "Helena Cortés Navarro",    "rut": "209123456", "edad": 48, "sexo": "F",
        "prevision_principal": "FONASA", "prevision_sub": "GES",
        "diagnostico": "Post-Op Abdomen Agudo", "diagnostico_cie10": "K65.0",
        "sintomas": "Dolor abdominal difuso, fiebre, peritonitis post-cirugía",
        "comorbilidades": "Obesidad", "unidad": "UTI", "cama": "UTI-03",
        "dias": 3, "horas_admision": 1.5,
    },
    {
        "nombre": "Ignacio Peña Moya",        "rut": "210234567", "edad": 55, "sexo": "M",
        "prevision_principal": "FONASA", "prevision_sub": "Libre Elección",
        "diagnostico": "Cetoacidosis Diabética", "diagnostico_cie10": "E10.1",
        "sintomas": "Hiperglicemia severa, vómitos, alteración de conciencia, pH 7.2",
        "comorbilidades": "DM1, IRC moderada", "unidad": "UTI", "cama": "UTI-04",
        "dias": 2, "horas_admision": 1.0,
    },
    # MQ
    {
        "nombre": "Javiera Godoy Soto",       "rut": "221345678", "edad": 39, "sexo": "F",
        "prevision_principal": "Isapre", "prevision_sub": "Cruz Blanca", "prevision_apellido": "Plan",
        "diagnostico": "Colecistitis Aguda Litiásica", "diagnostico_cie10": "K81.0",
        "sintomas": "Dolor en hipocondrio derecho, fiebre, Murphy positivo",
        "comorbilidades": "Obesidad", "unidad": "MQ", "cama": "MQ-01",
        "dias": 2, "horas_admision": 1.5,
    },
    {
        "nombre": "Kevin Araya Fuentes",      "rut": "232456789", "edad": 22, "sexo": "M",
        "prevision_principal": "FONASA", "prevision_sub": "Libre Elección",
        "diagnostico": "Apendicitis Aguda Complicada", "diagnostico_cie10": "K35.2",
        "sintomas": "Dolor fosa ilíaca derecha, signo de Blumberg, perforación",
        "comorbilidades": "Ninguna", "unidad": "MQ", "cama": "MQ-02",
        "dias": 1, "horas_admision": 0.5,
    },
    {
        "nombre": "Laura Ibáñez Castro",      "rut": "243567890", "edad": 72, "sexo": "F",
        "prevision_principal": "FONASA", "prevision_sub": "Ley Urgencia",
        "diagnostico": "EPOC Exacerbado con Infección", "diagnostico_cie10": "J44.1",
        "sintomas": "Disnea progresiva, expectoración purulenta, sibilancias difusas",
        "comorbilidades": "EPOC, Tabaquismo crónico", "unidad": "MQ", "cama": "MQ-03",
        "dias": 8, "horas_admision": 4.0,
    },
    {
        "nombre": "Marcelo Tapia Vega",       "rut": "254678901", "edad": 61, "sexo": "M",
        "prevision_principal": "Isapre", "prevision_sub": "Banmédica", "prevision_apellido": "CAEC",
        "diagnostico": "Hernia Inguinal Complicada", "diagnostico_cie10": "K40.3",
        "sintomas": "Tumoración inguinal no reductible, dolor agudo, signos de obstrucción",
        "comorbilidades": "HTA", "unidad": "MQ", "cama": "MQ-04",
        "dias": 3, "horas_admision": 1.5,
    },
    {
        "nombre": "Natalia Flores Reyes",     "rut": "265789012", "edad": 59, "sexo": "F",
        "prevision_principal": "Particular",
        "diagnostico": "Crisis Hipertensiva", "diagnostico_cie10": "I10",
        "sintomas": "Cefalea intensa, PA 210/130, visión borrosa, epistaxis",
        "comorbilidades": "HTA, Dislipidemia, Obesidad", "unidad": "MQ", "cama": "MQ-05",
        "dias": 4, "horas_admision": 2.0,
    },
    {
        "nombre": "Orlando Bravo Sobarzo",    "rut": "276890123", "edad": 43, "sexo": "M",
        "prevision_principal": "FONASA", "prevision_sub": "GES",
        "diagnostico": "Cólico Renal Obstructivo", "diagnostico_cie10": "N20.0",
        "sintomas": "Dolor lumbar irradiado, hematuria, hidronefrosis en ecografía",
        "comorbilidades": "Ninguna", "unidad": "MQ", "cama": "MQ-06",
        "dias": 2, "horas_admision": 1.0,
    },
    # Recuperacion
    {
        "nombre": "Pamela Cuevas Ortiz",      "rut": "287901234", "edad": 46, "sexo": "F",
        "prevision_principal": "Isapre", "prevision_sub": "Colmena", "prevision_apellido": "Plan",
        "diagnostico": "Post-Op Laparotomía Exploradora", "diagnostico_cie10": "Z09",
        "sintomas": "Dolor moderado controlado, tolerando líquidos, evolución favorable",
        "comorbilidades": "Ninguna", "unidad": "Recuperacion", "cama": "REC-01",
        "dias": 1, "horas_admision": 1.0,
    },
]

URGENCIAS_PACIENTES_DATA = [
    {
        "nombre": "Rodrigo Saavedra Núñez",   "rut": "298012345", "edad": 41, "sexo": "M",
        "prevision_principal": "FONASA", "prevision_sub": "Libre Elección",
        "sintomas": "Dolor abdominal agudo en epigastrio, náuseas, vómitos repetidos",
        "comorbilidades": "Ninguna", "horas_espera": 0.8,
        "nivel_triage": None,
        "admision_completada": False, "atencion_medica_completada": False,
        "orden_hospitalizacion": False, "categoria_solicitada": None,
        "check_clinico": False, "check_admin": False,
    },
    {
        "nombre": "Sandra Valenzuela Molina", "rut": "309123456", "edad": 36, "sexo": "F",
        "prevision_principal": "Isapre", "prevision_sub": "Banmédica", "prevision_apellido": "Plan",
        "sintomas": "Cefalea intensa de inicio brusco, fotofobia, rigidez de nuca",
        "comorbilidades": "Migraña crónica", "horas_espera": 1.2,
        "nivel_triage": None,
        "admision_completada": False, "atencion_medica_completada": False,
        "orden_hospitalizacion": False, "categoria_solicitada": None,
        "check_clinico": False, "check_admin": False,
    },
    {
        "nombre": "Tomás Aguilar Espinoza",   "rut": "310234567", "edad": 27, "sexo": "M",
        "prevision_principal": "FONASA", "prevision_sub": "GES",
        "sintomas": "Disnea aguda, sibilancias audibles, SpO2 91%, musculatura accesoria",
        "comorbilidades": "Asma severa", "horas_espera": 2.1,
        "nivel_triage": 3,
        "admision_completada": False, "atencion_medica_completada": False,
        "orden_hospitalizacion": False, "categoria_solicitada": None,
        "check_clinico": False, "check_admin": False,
    },
    {
        "nombre": "Úrsula Medina Torres",     "rut": "321345678", "edad": 63, "sexo": "F",
        "prevision_principal": "FONASA", "prevision_sub": "Ley Urgencia",
        "sintomas": "Hemiparesia izquierda súbita, disartria, desviación de comisura",
        "comorbilidades": "HTA, Tabaquismo", "horas_espera": 1.5,
        "nivel_triage": 1,
        "admision_completada": True, "atencion_medica_completada": False,
        "orden_hospitalizacion": False, "categoria_solicitada": None,
        "check_clinico": False, "check_admin": False,
    },
    {
        "nombre": "Víctor Jara Meza",         "rut": "332456789", "edad": 79, "sexo": "M",
        "prevision_principal": "FONASA", "prevision_sub": "Ley Urgencia",
        "sintomas": "Síncope con trauma craneal, desorientación, bradicardia severa",
        "comorbilidades": "HTA, Cardiopatía, Marcapasos", "horas_espera": 4.5,
        "nivel_triage": 2,
        "admision_completada": True, "atencion_medica_completada": True,
        "orden_hospitalizacion": True, "categoria_solicitada": "UTI",
        "check_clinico": False, "check_admin": False,
    },
    {
        "nombre": "Wanda Rojas Contreras",    "rut": "343567890", "edad": 50, "sexo": "F",
        "prevision_principal": "Isapre", "prevision_sub": "Consalud", "prevision_apellido": "Plan",
        "sintomas": "Dolor torácico atípico, diaforesis, troponinas elevadas",
        "comorbilidades": "HTA, DM2, Obesidad", "horas_espera": 6.2,
        "nivel_triage": 2,
        "admision_completada": True, "atencion_medica_completada": True,
        "orden_hospitalizacion": True, "categoria_solicitada": "UCO UTI",
        "check_clinico": True, "check_admin": True,
    },
    {
        "nombre": "Xavier Acuña Palma",       "rut": "354678901", "edad": 35, "sexo": "M",
        "prevision_principal": "FONASA", "prevision_sub": "Libre Elección",
        "sintomas": "Fractura expuesta fémur derecho, hemorragia activa, hipotensión",
        "comorbilidades": "Ninguna", "horas_espera": 3.0,
        "nivel_triage": 2,
        "admision_completada": True, "atencion_medica_completada": True,
        "orden_hospitalizacion": True, "categoria_solicitada": "UTI",
        "check_clinico": True, "check_admin": True,
    },
]


# ── Funciones de seed ─────────────────────────────────────────────────────────

def seed_prevision_meta(db: Session):
    if db.query(models.PrevisionMeta).count() > 0:
        return
    for entry in PREVISION_META_DATA:
        db.add(models.PrevisionMeta(**entry))
    db.commit()


def seed_users():
    db = SessionLocal()
    try:
        for u in DEMO_USERS_DATA:
            exists = db.query(models.User).filter(models.User.username == u["username"]).first()
            if not exists:
                db.add(models.User(
                    username=u["username"],
                    full_name=u["full_name"],
                    hashed_password=get_password_hash(u["password"]),
                    role=u["role"],
                    is_active=True,
                    institucion="Clínica Santiago",
                ))
        db.commit()
    finally:
        db.close()


def seed_database():
    db = SessionLocal()
    try:
        seed_prevision_meta(db)

        if db.query(models.Cama).count() > 0:
            return

        ocupadas = {p["cama"] for p in MOCK_PACIENTES_DATA}

        for unidad, camas in CAMAS_CONFIG_DATA.items():
            for num in camas:
                if num in ocupadas:
                    estado = "ocupada"
                elif unidad == "Urgencia":
                    estado = random.choices(["libre", "limpieza"], weights=[75, 25])[0]
                else:
                    estado = random.choices(["libre", "limpieza"], weights=[85, 15])[0]
                db.add(models.Cama(numero=num, unidad=unidad, estado=estado))
        db.commit()

        now = datetime.now(timezone.utc)

        for p in MOCK_PACIENTES_DATA:
            fecha_ingreso = now - timedelta(days=p["dias"])
            fecha_hosp    = fecha_ingreso + timedelta(hours=p.get("horas_admision", 2.0))
            prev_principal = p.get("prevision_principal", "FONASA")
            paciente = models.Paciente(
                nombre=p["nombre"], rut=p["rut"], edad=p["edad"], sexo=p["sexo"],
                prevision_principal=prev_principal,
                prevision_sub=p.get("prevision_sub"),
                prevision_apellido=p.get("prevision_apellido"),
                sufijo_fonasa=_sufijo_fonasa(prev_principal),
                prevision=prev_principal,   # legado
                sintomas=p.get("sintomas"),
                diagnostico=p.get("diagnostico"),
                diagnostico_cie10=p.get("diagnostico_cie10"),
                comorbilidades=p["comorbilidades"],
                estado="hospitalizado",
                unidad=p["unidad"], fecha_ingreso=fecha_ingreso,
                fecha_hospitalizacion=fecha_hosp,
                dias_estadia=p["dias"],
                nivel_triage=random.choice([1, 2, 3]),
                admision_completada=True,
                fecha_admision=fecha_ingreso + timedelta(minutes=30),
                pagare_firmado=True,
                atencion_medica_completada=True,
                fecha_atencion_medica=fecha_ingreso + timedelta(hours=1),
                orden_hospitalizacion=True,
                check_clinico=True, check_admin=True,
                fecha_doble_check=fecha_hosp - timedelta(minutes=30),
                fecha_asignacion_cama=fecha_hosp - timedelta(minutes=20),
                fecha_llegada_unidad=fecha_hosp,
            )
            db.add(paciente)
            db.commit()
            db.refresh(paciente)

            cama = db.query(models.Cama).filter(models.Cama.numero == p["cama"]).first()
            if cama:
                cama.paciente_id = paciente.id
                db.commit()

            db.add(models.Evento(paciente_id=paciente.id, tipo="ingreso",
                descripcion=f"Ingreso a Urgencias — {p.get('sintomas', p['diagnostico'])}", timestamp=fecha_ingreso))
            db.add(models.Evento(paciente_id=paciente.id, tipo="hospitalizacion",
                descripcion=f"Hospitalizado en {p['unidad']} — Cama {p['cama']}", timestamp=fecha_hosp))
        db.commit()

        for u in URGENCIAS_PACIENTES_DATA:
            fecha_ingreso = now - timedelta(hours=u["horas_espera"])
            fecha_orden = fecha_admision = fecha_atencion = fecha_doble_check = None

            if u.get("admision_completada"):
                fecha_admision = fecha_ingreso + timedelta(minutes=20)
            if u.get("atencion_medica_completada"):
                fecha_atencion = (fecha_admision or fecha_ingreso) + timedelta(minutes=40)
            if u["orden_hospitalizacion"]:
                fecha_orden = fecha_atencion or (fecha_ingreso + timedelta(hours=u["horas_espera"] * 0.5))
            if u["check_clinico"] and u["check_admin"]:
                fecha_doble_check = (fecha_orden or fecha_ingreso) + timedelta(minutes=30)

            prev_principal = u.get("prevision_principal", "FONASA")
            paciente = models.Paciente(
                nombre=u["nombre"], rut=u["rut"], edad=u["edad"], sexo=u["sexo"],
                prevision_principal=prev_principal,
                prevision_sub=u.get("prevision_sub"),
                prevision_apellido=u.get("prevision_apellido"),
                sufijo_fonasa=_sufijo_fonasa(prev_principal),
                prevision=prev_principal,
                sintomas=u.get("sintomas"),
                comorbilidades=u["comorbilidades"], estado="urgencias",
                unidad=None, fecha_ingreso=fecha_ingreso,
                valor_cuenta_estimado=0, dias_estadia=0,
                nivel_triage=u["nivel_triage"],
                admision_completada=u.get("admision_completada", False),
                fecha_admision=fecha_admision,
                pagare_firmado=u.get("admision_completada", False),
                atencion_medica_completada=u.get("atencion_medica_completada", False),
                fecha_atencion_medica=fecha_atencion,
                categoria_solicitada=u.get("categoria_solicitada"),
                orden_hospitalizacion=u["orden_hospitalizacion"],
                fecha_orden=fecha_orden,
                check_clinico=u["check_clinico"],
                check_admin=u["check_admin"],
                fecha_doble_check=fecha_doble_check,
            )
            db.add(paciente)
            db.commit()
            db.refresh(paciente)

            db.add(models.Evento(paciente_id=paciente.id, tipo="ingreso",
                descripcion=f"Ingreso a Urgencias — {u.get('sintomas', 'Sin descripción')}", timestamp=fecha_ingreso))
            if u["nivel_triage"] is not None:
                db.add(models.Evento(paciente_id=paciente.id, tipo="triage",
                    descripcion=f"Triage: {TRIAGE_LABELS.get(u['nivel_triage'], str(u['nivel_triage']))}",
                    timestamp=fecha_ingreso + timedelta(minutes=10)))
            if u.get("admision_completada") and fecha_admision:
                db.add(models.Evento(paciente_id=paciente.id, tipo="admision",
                    descripcion="Admisión completada — Pagaré firmado", timestamp=fecha_admision))
            if u.get("atencion_medica_completada") and fecha_atencion:
                db.add(models.Evento(paciente_id=paciente.id, tipo="atencion_medica",
                    descripcion="Atención médica completada — Orden emitida", timestamp=fecha_atencion))
            if u["orden_hospitalizacion"] and fecha_orden:
                db.add(models.Evento(paciente_id=paciente.id, tipo="orden",
                    descripcion=f"Orden de hospitalización — Categoría: {u.get('categoria_solicitada', '—')}",
                    timestamp=fecha_orden))
            if u["check_clinico"] and u["check_admin"] and fecha_doble_check:
                db.add(models.Evento(paciente_id=paciente.id, tipo="doble_check",
                    descripcion="Doble validación completada — listo para cama", timestamp=fecha_doble_check))
        db.commit()

    finally:
        db.close()
