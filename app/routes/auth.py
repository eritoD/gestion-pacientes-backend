from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.database import get_db
from app import models
from app.auth import get_current_user, get_current_admin, get_password_hash, verify_password, create_access_token
from app.schemas import LoginRequest, UserCreate, UserUpdate
from app.config import VALID_ROLES

router = APIRouter(prefix="/api/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

# Contador en memoria de intentos fallidos: {ip: [timestamp, ...]}
_failed_attempts: dict = {}
_MAX_ATTEMPTS = 10
_LOCKOUT_SECONDS = 300  # 5 minutos


def _check_brute_force(ip: str):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).timestamp()
    attempts = [t for t in _failed_attempts.get(ip, []) if now - t < _LOCKOUT_SECONDS]
    _failed_attempts[ip] = attempts
    if len(attempts) >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos. Espera {_LOCKOUT_SECONDS // 60} minutos."
        )


def _register_failed(ip: str):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).timestamp()
    _failed_attempts.setdefault(ip, []).append(now)


def _clear_failed(ip: str):
    _failed_attempts.pop(ip, None)


@router.post("/login")
@limiter.limit("20/minute")
def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    ip = get_remote_address(request)
    _check_brute_force(ip)

    user = db.query(models.User).filter(models.User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        _register_failed(ip)
        # Mensaje genérico para no revelar si el usuario existe
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario desactivado")

    _clear_failed(ip)
    token = create_access_token(data={"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id, "username": user.username,
            "full_name": user.full_name, "role": user.role,
            "institucion": user.institucion,
        },
    }


@router.get("/me")
def get_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id, "username": current_user.username,
        "full_name": current_user.full_name, "role": current_user.role,
        "institucion": current_user.institucion,
    }


@router.get("/users")
def list_users(current_user: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return [
        {"id": u.id, "username": u.username, "full_name": u.full_name,
         "role": u.role, "is_active": u.is_active, "created_at": u.created_at,
         "institucion": u.institucion}
        for u in users
    ]


@router.post("/users")
def create_user(data: UserCreate, current_user: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Rol inválido. Opciones: {', '.join(VALID_ROLES)}")
    user = models.User(
        username=data.username, full_name=data.full_name,
        hashed_password=get_password_hash(data.password),
        role=data.role, institucion=data.institucion,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "full_name": user.full_name,
            "role": user.role, "is_active": user.is_active, "institucion": user.institucion}


@router.put("/users/{user_id}")
def update_user(user_id: int, data: UserUpdate, current_user: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.username == "admin" and data.role and data.role != "admin":
        raise HTTPException(status_code=400, detail="No se puede cambiar el rol del administrador principal")
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        if data.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Rol inválido")
        user.role = data.role
    if data.password:
        if len(data.password) < 8:
            raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")
        user.hashed_password = get_password_hash(data.password)
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.institucion is not None:
        user.institucion = data.institucion
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "full_name": user.full_name,
            "role": user.role, "is_active": user.is_active, "institucion": user.institucion}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, current_user: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.username == "admin":
        raise HTTPException(status_code=400, detail="No se puede eliminar el administrador principal")
    db.delete(user)
    db.commit()
    return {"ok": True}
