from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime, timezone


def _utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String, unique=True, index=True, nullable=False)
    full_name       = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    role            = Column(String, default="viewer")  # admin | viewer
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime(timezone=True), default=_utc_now)
    institucion     = Column(String, nullable=True, default="Clínica Santiago")


class Cama(Base):
    __tablename__ = "camas"

    id          = Column(Integer, primary_key=True, index=True)
    numero      = Column(String, unique=True, index=True)
    unidad      = Column(String, index=True)
    estado      = Column(String, default="libre", index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id"), nullable=True)

    paciente = relationship("Paciente", back_populates="cama")


class Paciente(Base):
    __tablename__ = "pacientes"

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String, nullable=False)
    rut         = Column(String, index=True)
    edad        = Column(Integer)
    sexo        = Column(String)
    direccion   = Column(String, nullable=True)

    # Previsión jerárquica
    prevision_principal = Column(String, nullable=True)   # FONASA | Isapre | Particular | FF.AA.
    prevision_sub       = Column(String, nullable=True)   # subclasificación según principal
    prevision_apellido  = Column(String, nullable=True)   # apellido de cuenta (GES, CAEC, Plan...)
    sufijo_fonasa       = Column(Boolean, default=False)
    prevision           = Column(String, nullable=True)   # campo legado / alias

    # Clínico — separación estricta
    sintomas            = Column(Text, nullable=True)      # descripción síntomas triage (sin CIE-10)
    diagnostico         = Column(String, nullable=True)    # legado
    diagnostico_cie10   = Column(String, nullable=True)    # solo módulo médico

    comorbilidades = Column(String, default="")
    estado      = Column(String, default="urgencias", index=True)
    unidad      = Column(String, nullable=True)
    fecha_ingreso          = Column(DateTime(timezone=True), default=_utc_now)
    fecha_hospitalizacion  = Column(DateTime(timezone=True), nullable=True)
    fecha_alta             = Column(DateTime(timezone=True), nullable=True)
    valor_cuenta_estimado  = Column(Float, default=0.0)
    dias_estadia           = Column(Integer, default=0)

    # Flujo Urgencias
    nivel_triage          = Column(Integer, nullable=True)
    categoria_solicitada  = Column(String, nullable=True)
    orden_hospitalizacion = Column(Boolean, default=False, index=True)
    fecha_orden           = Column(DateTime(timezone=True), nullable=True)
    check_clinico         = Column(Boolean, default=False)
    check_admin           = Column(Boolean, default=False)
    fecha_doble_check     = Column(DateTime(timezone=True), nullable=True)
    fecha_asignacion_cama = Column(DateTime(timezone=True), nullable=True)
    fecha_llegada_unidad  = Column(DateTime(timezone=True), nullable=True)

    # Admisión administrativa
    admision_completada   = Column(Boolean, default=False)
    fecha_admision        = Column(DateTime(timezone=True), nullable=True)
    pagare_firmado        = Column(Boolean, default=False)

    # Atención Médica
    atencion_medica_completada = Column(Boolean, default=False)
    fecha_atencion_medica = Column(DateTime(timezone=True), nullable=True)
    indicaciones_medicas  = Column(Text, nullable=True)
    prescripciones        = Column(Text, nullable=True)

    # Contacto (solo módulo admin)
    telefono              = Column(String, nullable=True)
    contacto_emergencia   = Column(String, nullable=True)

    # Clínico adicional
    alergias              = Column(Text, nullable=True)
    medicamentos_actuales = Column(Text, nullable=True)
    grupo_sanguineo       = Column(String, nullable=True)
    peso_kg               = Column(Float, nullable=True)
    talla_cm              = Column(Integer, nullable=True)
    observaciones_clinicas= Column(Text, nullable=True)

    # Signos Vitales
    presion_arterial        = Column(String, nullable=True)
    frecuencia_cardiaca     = Column(Integer, nullable=True)
    temperatura             = Column(Float, nullable=True)
    saturacion_o2           = Column(Integer, nullable=True)
    frecuencia_respiratoria = Column(Integer, nullable=True)

    # Interconsulta
    interconsulta_pendiente  = Column(Boolean, default=False, index=True)
    tipo_interconsultor      = Column(String, nullable=True)
    fecha_interconsulta      = Column(DateTime(timezone=True), nullable=True)

    # Alta
    tipo_alta               = Column(String, nullable=True)   # voluntaria | disciplinaria | en_tratamiento | fallecimiento
    alta_probable           = Column(Boolean, default=False)  # pronostico alta mañana

    # Traslado interno
    traslado_pendiente      = Column(Boolean, default=False)
    indicacion_traslado     = Column(Text, nullable=True)
    unidad_traslado_destino = Column(String, nullable=True)

    # Relaciones
    cama     = relationship("Cama", back_populates="paciente", uselist=False)
    eventos  = relationship("Evento",  back_populates="paciente", cascade="all, delete-orphan")
    examenes = relationship("Examen",  back_populates="paciente", cascade="all, delete-orphan")
    archivos = relationship("Archivo", back_populates="paciente", cascade="all, delete-orphan")


class PrevisionMeta(Base):
    __tablename__ = "prevision_meta"
    id         = Column(Integer, primary_key=True, index=True)
    codigo     = Column(String, unique=True, nullable=False, index=True)
    label      = Column(String, nullable=False)
    tarifa_dia = Column(Integer, nullable=False, default=80_000)
    riesgo     = Column(String, nullable=False, default="Desconocido")
    cobertura  = Column(String, nullable=False, default="—")
    color      = Column(String, nullable=False, default="gray")


class Evento(Base):
    __tablename__ = "eventos"

    id          = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id"))
    tipo        = Column(String)
    descripcion = Column(String)
    timestamp   = Column(DateTime(timezone=True), default=_utc_now)
    usuario     = Column(String, default="Sistema")

    paciente = relationship("Paciente", back_populates="eventos")


class Examen(Base):
    __tablename__ = "examenes"

    id               = Column(Integer, primary_key=True, index=True)
    paciente_id      = Column(Integer, ForeignKey("pacientes.id"))
    tipo             = Column(String)
    nombre           = Column(String)
    estado           = Column(String, default="pendiente")
    urgente          = Column(Boolean, default=False)
    resultado        = Column(Text, nullable=True)
    fecha_solicitado = Column(DateTime(timezone=True), default=_utc_now)
    fecha_resultado  = Column(DateTime(timezone=True), nullable=True)

    paciente = relationship("Paciente", back_populates="examenes")


class Archivo(Base):
    __tablename__ = "archivos"

    id           = Column(Integer, primary_key=True, index=True)
    paciente_id  = Column(Integer, ForeignKey("pacientes.id"))
    nombre       = Column(String)
    tipo         = Column(String)
    descripcion  = Column(String, nullable=True)
    datos_b64    = Column(Text, nullable=True)
    mime_type    = Column(String, nullable=True)
    fecha_subida = Column(DateTime(timezone=True), default=_utc_now)

    paciente = relationship("Paciente", back_populates="archivos")
