VALID_ROLES = ("admin", "gestor", "jefatura", "medico", "enfermera", "administrativo", "viewer")

TRIAGE_LABELS = {
    0: "C0 — Parto/RN",
    1: "C1 — Riesgo Vital",
    2: "C2 — Emergencia",
    3: "C3 — Urgencia",
    4: "C4 — Urgencia Menor",
    5: "C5 — No Urgente",
}

TIPOS_ALTA_LABELS = {
    "voluntaria":        "Alta Voluntaria",
    "disciplinaria":     "Alta Disciplinaria",
    "en_tratamiento":    "Alta en Tratamiento",
    "fallecimiento":     "Alta por Fallecimiento",
    "mejorada":          "Alta Mejorada",
    "traslado":          "Alta Traslado",
    "retiro_voluntario": "Retiro Voluntario (Urgencias)",
    "fuga":              "Fuga — Paciente Abandona sin Aviso",
    "derivacion_externa":"Derivación a Otro Centro",
}
