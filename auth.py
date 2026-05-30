import os
import threading
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from cachetools import TTLCache
from database import db_pool, conectar_bd
from models import TokenData, LoginRequest
from helpers import _auth_cache, _cache_lock

# ─── SEGURIDAD: JWT y Bcrypt ──────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY no definida. Agrégala en las variables de entorno de Render.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 días

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas, token expirado o cuenta desactivada",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id_tienda: int = payload.get("id_tienda")
        id_usuario: int = payload.get("id_usuario")
        if id_tienda is None or id_usuario is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    cache_key = f"{id_tienda}:{id_usuario}"
    with _cache_lock:
        if cache_key in _auth_cache:
            return _auth_cache[cache_key]

    conexion = db_pool.get_connection()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.activa, u.id_usuario, u.rol
            FROM tiendas t
            LEFT JOIN usuarios u ON u.id_usuario = %s AND u.activo = 1 AND u.id_tienda = t.id_tienda
            WHERE t.id_tienda = %s
        """, (id_usuario, id_tienda))
        estado = cursor.fetchone()
        if not estado or not estado['activa'] or not estado['id_usuario']:
            raise credentials_exception

        # ← CORRECCIÓN CRÍTICA: el rol viene de la BD, no del token
        rol_verificado = estado['rol']

        token_data = TokenData(id_tienda=id_tienda, id_usuario=id_usuario, rol=rol_verificado)
        with _cache_lock:
            _auth_cache[cache_key] = token_data
        return token_data
    finally:
        if cursor is not None:
            cursor.close()
        conexion.close()


# ─── Auth Endpoint ────────────────────────────────────────────────────────────
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def register_auth_routes(app):
    @app.post("/login")
    @limiter.limit("10/minute")
    def login(request: Request, datos: LoginRequest):

        conexion = conectar_bd()
        cursor = None
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("""
                        SELECT id_usuario, id_tienda, password_hash, rol 
                        FROM usuarios 
                        WHERE username = %s AND activo = 1
                    """, (datos.username,)
            )
            user = cursor.fetchone()
            password_hash = user[
                'password_hash'] if user else "$2b$12$KIXnotarealhashjustpaddingtomakeittakesametime00000000000"
            if not user or not pwd_context.verify(datos.password, password_hash):
                raise HTTPException(status_code=401, detail="Credenciales inválidas")

            if user.get('rol') == 'superadmin':
                expire = datetime.now(tz=timezone.utc) + timedelta(days=2)
            else:
                expire = datetime.now(tz=timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            # ────────────────────────────────────────────────────────────
            encoded_jwt = jwt.encode(
                {"id_tienda": user['id_tienda'], "id_usuario": user['id_usuario'],
                 "rol": user.get('rol', 'cajero'), "exp": expire},
                SECRET_KEY, algorithm=ALGORITHM
            )
            return {"access_token": encoded_jwt, "token_type": "bearer", "rol": user.get('rol', 'cajero')}
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()