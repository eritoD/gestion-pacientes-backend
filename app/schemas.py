import base64
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime

# Tipos de archivo permitidos para documentos clínicos
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg", "image/png",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB en bytes → base64 ~13.3 MB de string


class PacienteOut(BaseModel):
    id: int
    nombre: str
    rut: str
    edad: int
    sexo: str
    # Previsión jerárquica
    prevision_principal: Optional[str] = None
    prevision_sub: Optional[str] = None
    prevision_apellido: Optional[str] = None
    sufijo_fonasa: bool = False
    prevision: Optional[str] = None   # campo legado
    # Clínico separado
    sintomas: Optional[str] = None
    diagnostico: Optional[str] = None
    diagnostico_cie10: Optional[str] = None
    comorbilidades: str = ""
    direccion: Optional[str] = None
    estado: str
    unidad: Optional[str]
    fecha_ingreso: datetime
    fecha_hospitalizacion: Optional[datetime]
    fecha_alta: Optional[datetime]
    valor_cuenta_estimado: float
    dias_estadia: int
    cama_numero: Optional[str] = None
    # Contacto (solo admin)
    telefono: Optional[str] = None
    contacto_emergencia: Optional[str] = None
    # Clínico adicional
    alergias: Optional[str] = None
    medicamentos_actuales: Optional[str] = None
    grupo_sanguineo: Optional[str] = None
    peso_kg: Optional[float] = None
    talla_cm: Optional[int] = None
    observaciones_clinicas: Optional[str] = None
    # Flujo urgencias
    nivel_triage: Optional[int] = None
    categoria_solicitada: Optional[str] = None
    orden_hospitalizacion: bool = False
    fecha_orden: Optional[datetime] = None
    check_clinico: bool = False
    check_admin: bool = False
    fecha_doble_check: Optional[datetime] = None
    fecha_asignacion_cama: Optional[datetime] = None
    fecha_llegada_unidad: Optional[datetime] = None
    # Admisión
    admision_completada: bool = False
    fecha_admision: Optional[datetime] = None
    pagare_firmado: bool = False
    # Atención Médica
    atencion_medica_completada: bool = False
    fecha_atencion_medica: Optional[datetime] = None
    indicaciones_medicas: Optional[str] = None
    prescripciones: Optional[str] = None
    # Signos Vitales
    presion_arterial: Optional[str] = None
    frecuencia_cardiaca: Optional[int] = None
    temperatura: Optional[float] = None
    saturacion_o2: Optional[int] = None
    frecuencia_respiratoria: Optional[int] = None
    # Interconsulta
    interconsulta_pendiente: bool = False
    tipo_interconsultor: Optional[str] = None
    fecha_interconsulta: Optional[datetime] = None
    # Alta
    tipo_alta: Optional[str] = None
    alta_probable: bool = False
    # Traslado
    traslado_pendiente: bool = False
    indicacion_traslado: Optional[str] = None
    unidad_traslado_destino: Optional[str] = None

    class Config:
        from_attributes = True


class CamaOut(BaseModel):
    id: int
    numero: str
    unidad: str
    estado: str
    paciente: Optional[PacienteOut] = None

    class Config:
        from_attributes = True


class PacienteCreate(BaseModel):
    nombre: str
    rut: str
    edad: int
    sexo: str
    direccion: Optional[str] = None
    # Previsión jerárquica
    prevision_principal: str
    prevision_sub: Optional[str] = None
    prevision_apellido: Optional[str] = None
    # Contacto administrativo
    telefono: Optional[str] = None
    contacto_emergencia: Optional[str] = None
    # Clínico básico opcional al ingreso
    comorbilidades: str = ""
    alergias: Optional[str] = None
    medicamentos_actuales: Optional[str] = None
    grupo_sanguineo: Optional[str] = None
    peso_kg: Optional[float] = None
    talla_cm: Optional[int] = None


class HospitalizarData(BaseModel):
    nueva_unidad: str
    nueva_cama_numero: str


class DatosClinicosUpdate(BaseModel):
    telefono: Optional[str] = None
    contacto_emergencia: Optional[str] = None
    alergias: Optional[str] = None
    medicamentos_actuales: Optional[str] = None
    grupo_sanguineo: Optional[str] = None
    peso_kg: Optional[float] = None
    talla_cm: Optional[int] = None
    observaciones_clinicas: Optional[str] = None


class TriageData(BaseModel):
    nivel_triage: int           # 0-5 (C1-C5)
    sintomas: Optional[str] = None  # descripción libre de síntomas — NO CIE-10
    comorbilidades: Optional[str] = None
    presion_arterial: Optional[str] = None
    frecuencia_cardiaca: Optional[int] = None
    temperatura: Optional[float] = None
    saturacion_o2: Optional[int] = None
    frecuencia_respiratoria: Optional[int] = None


class AdmisionData(BaseModel):
    pagare_firmado: bool = True
    telefono: Optional[str] = None
    contacto_emergencia: Optional[str] = None
    direccion: Optional[str] = None
    prevision_principal: Optional[str] = None
    prevision_sub: Optional[str] = None
    prevision_apellido: Optional[str] = None


class AtencionMedicaData(BaseModel):
    observaciones_clinicas: Optional[str] = None
    indicaciones_medicas: Optional[str] = None
    categoria_solicitada: str                  # UCI | UTI | MQ | UCO UI | UCO UTI


class OrdenHospitalizacionData(BaseModel):
    categoria_solicitada: str


class DobleCheckData(BaseModel):
    check_clinico: bool
    check_admin: bool


class ExamenOut(BaseModel):
    id: int
    tipo: str
    nombre: str
    estado: str
    urgente: bool
    resultado: Optional[str]
    fecha_solicitado: datetime
    fecha_resultado: Optional[datetime]

    class Config:
        from_attributes = True


class ExamenCreate(BaseModel):
    tipo: str
    nombre: str
    urgente: bool = False


class ExamenResultado(BaseModel):
    resultado: str


class ArchivoOut(BaseModel):
    id: int
    nombre: str
    tipo: str
    descripcion: Optional[str]
    mime_type: Optional[str]
    datos_b64: Optional[str]
    fecha_subida: datetime

    class Config:
        from_attributes = True


class ArchivoCreate(BaseModel):
    nombre: str
    tipo: str
    descripcion: Optional[str] = None
    datos_b64: Optional[str] = None
    mime_type: Optional[str] = None

    @field_validator("mime_type")
    @classmethod
    def validar_mime(cls, v):
        if v and v not in ALLOWED_MIME_TYPES:
            raise ValueError(f"Tipo de archivo no permitido: {v}")
        return v

    @field_validator("datos_b64")
    @classmethod
    def validar_tamanio(cls, v):
        if v:
            raw_size = len(v) * 3 // 4
            if raw_size > MAX_FILE_SIZE_BYTES:
                raise ValueError(f"Archivo demasiado grande. Máximo permitido: 10 MB")
        return v


class NotaCreate(BaseModel):
    texto: str


class AltaData(BaseModel):
    tipo_alta: str  # voluntaria | disciplinaria | en_tratamiento | fallecimiento


class TrasladoInternoData(BaseModel):
    unidad_destino: str
    indicacion_medica: str


class InterconsultaData(BaseModel):
    tipo_interconsultor: str


class AtenderInterconsultaData(BaseModel):
    nota: Optional[str] = None
    diagnostico_actualizado: Optional[str] = None


class ReservarCamaData(BaseModel):
    paciente_id: Optional[int] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    role: str = "viewer"
    institucion: Optional[str] = "Clínica Santiago"


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    institucion: Optional[str] = None


class PrevisionMetaOut(BaseModel):
    id: int
    codigo: str
    label: str
    tarifa_dia: int
    riesgo: str
    cobertura: str
    color: str

    class Config:
        from_attributes = True


class PrevisionMetaUpdate(BaseModel):
    label: Optional[str] = None
    tarifa_dia: Optional[int] = None
    riesgo: Optional[str] = None
    cobertura: Optional[str] = None
    color: Optional[str] = None
