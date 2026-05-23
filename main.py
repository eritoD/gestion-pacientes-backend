import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

from app.database import engine
from app import models
from app.auth import SECRET_KEY, ALGORITHM
from app.seed import seed_users, seed_database
from app.routes import auth, camas, pacientes, urgencias, examenes, dashboard, configuracion

# En producción, las migraciones las maneja Alembic (alembic upgrade head).
# create_all se mantiene para conveniencia en desarrollo local.
models.Base.metadata.create_all(bind=engine)

seed_users()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_database()
    yield


# Rate limiter — protege el endpoint de login contra brute force
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="GOL — Gestión de Pacientes API",
    lifespan=lifespan,
    docs_url="/api/docs" if os.getenv("APP_ENV") == "development" else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
# En producción, define CORS_ORIGINS en .env con el dominio real
_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:3001")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Security headers ──────────────────────────────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if os.getenv("APP_ENV") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'"
        )
    return response


# ── Auth middleware ───────────────────────────────────────────────────────────
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    PUBLIC_PATHS = {"/api/auth/login"}
    if not path.startswith("/api/") or path in PUBLIC_PATHS:
        return await call_next(request)
    if request.method == "OPTIONS":
        return await call_next(request)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "No autenticado"})
    token = auth_header.split(" ", 1)[1]
    try:
        from jose import jwt as jose_jwt, JWTError as JoseJWTError
        payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise JoseJWTError()
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Token inválido o expirado"})
    return await call_next(request)


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(camas.router)
app.include_router(pacientes.router)
app.include_router(urgencias.router)
app.include_router(examenes.router)
app.include_router(dashboard.router)
app.include_router(configuracion.router)


# ── Estáticos de React ────────────────────────────────────────────────────────
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
