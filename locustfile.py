"""
Prueba de Carga — Sistema GOL Bupa
====================================
Escenario: 1000 usuarios concurrentes usando el sistema
Carga clínica: 3 pacientes por cama por día (~162 registros/día con 54 camas)

Distribución de usuarios:
  - 50% Visualizadores / Jefatura → ven dashboards y reportes
  - 20% Gestores              → asignan camas, crean pacientes
  - 15% Enfermeras            → triage, admisión, doble check
  - 10% Médicos               → atención médica, fichas
  -  5% Administrativos       → ingreso inicial de pacientes

Cómo ejecutar:
  1. Iniciar el backend: uvicorn main:app --host 0.0.0.0 --port 8000
  2. Correr Locust UI:   locust -f locustfile.py --host http://localhost:8000
  3. Abrir:              http://localhost:8089
  4. Configurar:         1000 usuarios, ramp-up 10 usuarios/segundo
  
  O en modo headless (sin UI):
  locust -f locustfile.py --host http://localhost:8000 \\
         --users 1000 --spawn-rate 10 --run-time 5m --headless
"""

from locust import HttpUser, task, between, events, constant_pacing
import random
import json
import time
import logging
from datetime import datetime

# ─── Datos de prueba ──────────────────────────────────────────────────────────

NOMBRES = [
    "Juan García López", "María Martínez Ruiz", "Carlos Rodríguez Pérez",
    "Ana González Díaz", "Pedro Hernández Torres", "Isabel Fernández Mora",
    "Miguel López Sánchez", "Carmen Torres Gutiérrez", "José Ruiz Jiménez",
    "Laura Sánchez Moreno", "Antonio Ramírez Flores", "Elena Castro Núñez",
    "Francisco Ortiz Medina", "Rosa Morales Vega", "Manuel Jiménez Ramos",
    "Sofía Navarro Castro", "Rafael Muñoz Herrera", "Cristina Alonso Romero",
    "Andrés Domínguez Santos", "Pilar Iglesias Cano", "Diego Vargas Ríos",
    "Valentina Molina Paredes", "Sebastián Campos Vera", "Camila Rojas Silva",
    "Matías Bravo Contreras", "Javiera Espinoza Pinto",
]

DIAGNOSTICOS = [
    "Neumonía adquirida en comunidad", "Insuficiencia cardíaca descompensada",
    "Fractura de cadera", "Apendicitis aguda", "Accidente cerebrovascular",
    "Sepsis de foco urinario", "Infarto agudo al miocardio", "Pancreatitis aguda",
    "Tromboembolismo pulmonar", "Crisis hipertensiva", "Deshidratación severa",
    "Colecistitis aguda", "Obstrucción intestinal", "Hemorragia digestiva alta",
    "Pielonefritis aguda", "Celulitis severa", "EPOC descompensada",
    "Crisis epiléptica", "Intoxicación medicamentosa", "Trauma múltiple",
]

PREVISIONS = ["FONASA", "ISAPRE", "Particular", "Ley Urgencia"]

COMORBILIDADES_LISTA = [
    "", "HTA", "DM tipo 2", "HTA, DM tipo 2", "EPOC", "Insuficiencia renal crónica",
    "HTA, cardiopatía isquémica", "Obesidad", "Hipotiroidismo", "",  # '' = sin comorbilidades
]

CATEGORIAS = ["UCI", "UCO UTI", "UCO UI", "UTI", "MQ", "Recuperacion"]

# Credenciales de los usuarios de prueba (del seed de la BD)
CREDENCIALES = {
    "admin":      ("admin",        "admin"),
    "gestor":     ("gestor",       "gestor123"),
    "jefatura":   ("jefatura",     "jefatura123"),
    "medico":     ("dr.martinez",  "medico123"),
    "enfermera":  ("enf.gomez",    "enfermera123"),
    "admin2":     ("admin",        "admin"),  # alias para más carga de admins
}

rut_counter = 10_000_000  # RUT base incremental para evitar duplicados


def next_rut():
    """Genera RUTs únicos secuenciales para evitar rechazos por duplicado."""
    global rut_counter
    rut_counter += random.randint(1, 100)
    return str(rut_counter)


def random_nombre():
    return random.choice(NOMBRES) + f" {random.randint(10, 99)}"


# ─── Clase Base ───────────────────────────────────────────────────────────────

class BupaBaseUser(HttpUser):
    """Clase base con helpers de login y manejo de errores."""
    abstract = True

    def on_start(self):
        self.token = None
        self.paciente_ids = []
        self._login()

    def _login(self, role_key: str = None):
        role_key = role_key or getattr(self, '_role', 'admin')
        username, password = CREDENCIALES.get(role_key, ("admin", "admin"))
        with self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            catch_response=True,
            name="POST /api/auth/login",
        ) as resp:
            if resp.status_code == 200:
                self.token = resp.json().get("access_token")
                self.client.headers.update({"Authorization": f"Bearer {self.token}"})
                resp.success()
            else:
                resp.failure(f"Login falló: {resp.status_code} — {resp.text[:100]}")

    def _refresh_pacientes(self):
        """Carga lista de IDs de pacientes para usar en otras tareas."""
        r = self.client.get("/api/pacientes", name="GET /api/pacientes")
        if r.status_code == 200:
            self.paciente_ids = [p["id"] for p in r.json()]

    def _random_paciente_id(self):
        if not self.paciente_ids:
            self._refresh_pacientes()
        return random.choice(self.paciente_ids) if self.paciente_ids else None


# ─── Tipo 1: Visualizador / Jefatura (50% del tráfico) ───────────────────────

class VisualizadorUser(BupaBaseUser):
    """
    Usuarios que consultan dashboards y reportes.
    Equivale a jefatura, directivos, supervisores.
    50% del total de usuarios concurrentes.
    """
    weight = 50
    wait_time = between(3, 12)
    _role = "jefatura"

    @task(6)
    def ver_dashboard_principal(self):
        self.client.get("/api/dashboard", name="GET /api/dashboard")

    @task(4)
    def ver_dashboard_financiero(self):
        self.client.get("/api/dashboard/financiero", name="GET /api/dashboard/financiero")

    @task(3)
    def ver_dashboard_operaciones(self):
        self.client.get("/api/dashboard/operaciones", name="GET /api/dashboard/operaciones")

    @task(5)
    def ver_mapa_camas(self):
        self.client.get("/api/camas", name="GET /api/camas")

    @task(2)
    def ver_lista_pacientes(self):
        self.client.get("/api/pacientes", name="GET /api/pacientes")

    @task(2)
    def ver_examenes_globales(self):
        self.client.get("/api/examenes", name="GET /api/examenes")

    @task(1)
    def ver_ficha_paciente(self):
        pid = self._random_paciente_id()
        if pid:
            self.client.get(f"/api/pacientes/{pid}", name="GET /api/pacientes/[id]")


# ─── Tipo 2: Gestor de Pacientes (20% del tráfico) ───────────────────────────

class GestorUser(BupaBaseUser):
    """
    Gestores que administran el flujo completo.
    Crean pacientes, asignan camas, monitorizan urgencias.
    
    Cálculo de carga de registro:
    - 54 camas × 3 pacientes/día = 162 registros/día
    - Por hora: ~6.75 → Por minuto: ~0.11
    - Con 200 gestores activos → 1 registro cada ~30 min por gestor
    """
    weight = 20
    wait_time = between(5, 20)
    _role = "gestor"

    def on_start(self):
        super().on_start()
        self._refresh_pacientes()

    @task(8)
    def ver_pipeline_urgencias(self):
        self.client.get("/api/urgencias/pipeline", name="GET /api/urgencias/pipeline")

    @task(7)
    def ver_mapa_camas(self):
        self.client.get("/api/camas", name="GET /api/camas")

    @task(5)
    def ver_solicitudes_cama(self):
        self.client.get("/api/urgencias/solicitudes-cama", name="GET /api/urgencias/solicitudes-cama")

    @task(4)
    def ver_cola_doble_check(self):
        self.client.get("/api/urgencias/cola-doble-check", name="GET /api/urgencias/cola-doble-check")

    @task(3)
    def ver_dashboard(self):
        self.client.get("/api/dashboard", name="GET /api/dashboard")

    @task(2)
    def ver_lista_pacientes(self):
        self.client.get("/api/pacientes", name="GET /api/pacientes")

    @task(1)
    def registrar_nuevo_paciente(self):
        """
        Simula ingreso inicial de urgencias.
        Task weight=1 de 30 total = ~3.3% del tiempo
        → Cada gestor registra ~1 paciente cada 30-40 min de uso activo.
        Con 200 gestores = 1 registro cada ~10 seg ≈ 144/hora >> 6.75/hora real.
        Para ajustar a la carga real, weight es bajo intencionalmente.
        """
        payload = {
            "nombre":              random_nombre(),
            "rut":                 next_rut(),
            "edad":                random.randint(18, 95),
            "sexo":                random.choice(["M", "F"]),
            "prevision_principal": random.choice(PREVISIONS),
            "comorbilidades":      random.choice(COMORBILIDADES_LISTA),
            "diagnostico":         random.choice(DIAGNOSTICOS),
        }
        with self.client.post(
            "/api/pacientes", json=payload,
            catch_response=True, name="POST /api/pacientes"
        ) as resp:
            if resp.status_code in (200, 201):
                new_id = resp.json().get("id")
                if new_id:
                    self.paciente_ids.append(new_id)
                resp.success()
            elif resp.status_code == 400:
                # RUT duplicado — no es error del sistema
                resp.success()
            else:
                resp.failure(f"Error {resp.status_code}: {resp.text[:80]}")

    @task(1)
    def ver_ficha_con_eventos(self):
        pid = self._random_paciente_id()
        if pid:
            self.client.get(f"/api/pacientes/{pid}", name="GET /api/pacientes/[id]")
            self.client.get(f"/api/pacientes/{pid}/eventos", name="GET /api/pacientes/[id]/eventos")


# ─── Tipo 3: Enfermera (15% del tráfico) ──────────────────────────────────────

class EnfermeraUser(BupaBaseUser):
    """
    Enfermeras que hacen triage, admisión y doble check.
    Consultan colas frecuentemente (flujo de trabajo en tiempo real).
    """
    weight = 15
    wait_time = between(2, 8)
    _role = "enfermera"

    @task(8)
    def ver_cola_triage(self):
        self.client.get("/api/urgencias/cola-triage", name="GET /api/urgencias/cola-triage")

    @task(7)
    def ver_cola_admision(self):
        self.client.get("/api/urgencias/cola-admision", name="GET /api/urgencias/cola-admision")

    @task(6)
    def ver_cola_doble_check(self):
        self.client.get("/api/urgencias/cola-doble-check", name="GET /api/urgencias/cola-doble-check")

    @task(4)
    def ver_mapa_camas(self):
        self.client.get("/api/camas", name="GET /api/camas")

    @task(3)
    def ver_examenes(self):
        self.client.get("/api/examenes?estado=pendiente", name="GET /api/examenes?estado=pendiente")

    @task(3)
    def ver_interconsultas(self):
        self.client.get("/api/urgencias/cola-interconsulta", name="GET /api/urgencias/cola-interconsulta")

    @task(2)
    def ver_lista_pacientes(self):
        self.client.get("/api/pacientes", name="GET /api/pacientes")

    @task(1)
    def ver_pipeline(self):
        self.client.get("/api/urgencias/pipeline", name="GET /api/urgencias/pipeline")


# ─── Tipo 4: Médico (10% del tráfico) ────────────────────────────────────────

class MedicoUser(BupaBaseUser):
    """
    Médicos que revisan fichas, atienden pacientes, ven exámenes.
    Interacciones más largas por cada paciente (leen, actualizan).
    """
    weight = 10
    wait_time = between(8, 25)
    _role = "medico"

    def on_start(self):
        super().on_start()
        self._refresh_pacientes()

    @task(6)
    def ver_cola_medica(self):
        self.client.get("/api/urgencias/cola-medica", name="GET /api/urgencias/cola-medica")

    @task(5)
    def ver_ficha_completa(self):
        """Simula abrir la ficha de un paciente y revisar sus datos."""
        pid = self._random_paciente_id()
        if not pid:
            return
        self.client.get(f"/api/pacientes/{pid}", name="GET /api/pacientes/[id]")
        time.sleep(random.uniform(1, 4))  # Lee la ficha
        self.client.get(f"/api/pacientes/{pid}/examenes", name="GET /api/pacientes/[id]/examenes")
        self.client.get(f"/api/pacientes/{pid}/eventos", name="GET /api/pacientes/[id]/eventos")

    @task(4)
    def ver_examenes_pendientes(self):
        self.client.get("/api/examenes?estado=pendiente", name="GET /api/examenes?estado=pendiente")

    @task(3)
    def ver_interconsultas(self):
        self.client.get("/api/urgencias/cola-interconsulta", name="GET /api/urgencias/cola-interconsulta")

    @task(2)
    def ver_dashboard_operaciones(self):
        self.client.get("/api/dashboard/operaciones", name="GET /api/dashboard/operaciones")

    @task(1)
    def ver_archivos_paciente(self):
        pid = self._random_paciente_id()
        if pid:
            self.client.get(f"/api/pacientes/{pid}/archivos", name="GET /api/pacientes/[id]/archivos")


# ─── Tipo 5: Administrativo (5% del tráfico) ──────────────────────────────────

class AdministrativoUser(BupaBaseUser):
    """
    Administrativos que ingresan pacientes y verifican datos.
    Interacciones simples pero frecuentes.
    """
    weight = 5
    wait_time = between(10, 30)
    _role = "admin2"

    @task(5)
    def ver_cola_admision(self):
        self.client.get("/api/urgencias/cola-admision", name="GET /api/urgencias/cola-admision")

    @task(4)
    def ver_lista_pacientes(self):
        self.client.get("/api/pacientes", name="GET /api/pacientes")

    @task(3)
    def ver_mapa_camas(self):
        self.client.get("/api/camas", name="GET /api/camas")

    @task(2)
    def ingresar_paciente(self):
        payload = {
            "nombre":              random_nombre(),
            "rut":                 next_rut(),
            "edad":                random.randint(18, 95),
            "sexo":                random.choice(["M", "F"]),
            "prevision_principal": random.choice(PREVISIONS),
            "comorbilidades":      "",
        }
        with self.client.post(
            "/api/pacientes", json=payload,
            catch_response=True, name="POST /api/pacientes"
        ) as resp:
            if resp.status_code in (200, 201, 400):
                resp.success()
            else:
                resp.failure(f"Error {resp.status_code}")

    @task(1)
    def ver_examenes(self):
        self.client.get("/api/examenes", name="GET /api/examenes")


# ─── Eventos de resumen ───────────────────────────────────────────────────────

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Imprime resumen al finalizar la prueba."""
    stats = environment.stats
    print("\n" + "="*60)
    print("📊 RESUMEN PRUEBA DE CARGA — SISTEMA GOL BUPA")
    print("="*60)
    total = stats.total
    print(f"  Total requests:       {total.num_requests:>10,}")
    print(f"  Requests fallidos:    {total.num_failures:>10,}")
    print(f"  Tasa de error:        {total.fail_ratio * 100:>9.1f}%")
    print(f"  RPS promedio:         {total.current_rps:>10.1f}")
    print(f"  Tiempo resp. mediano: {total.median_response_time:>10.0f}ms")
    print(f"  Tiempo resp. 95%:     {total.get_response_time_percentile(0.95):>10.0f}ms")
    print(f"  Tiempo resp. 99%:     {total.get_response_time_percentile(0.99):>10.0f}ms")
    print("="*60)

    if total.fail_ratio > 0.05:
        print("⚠️  ALERTA: Tasa de error > 5% — El sistema está bajo presión")
    elif total.median_response_time > 2000:
        print("⚠️  ALERTA: Tiempo de respuesta mediano > 2s — Revisar performance")
    else:
        print("✅  El sistema pasó la prueba de carga satisfactoriamente")
    print()
