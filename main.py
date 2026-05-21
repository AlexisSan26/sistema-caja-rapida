import os
import json
from typing import List, Literal
from pydantic import Field
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from enum import Enum
import mysql.connector
from dotenv import load_dotenv
import mysql.connector.pooling
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()

app = FastAPI()

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://alexissan26.github.io/sistema-caja-rapida/").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db_config = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 28257)),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'ssl_disabled': False,
    'time_zone': '-06:00',
}

# ─── RENDIMIENTO: Pool de conexiones a 8 ──────────────────────────────────────
db_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="cajapool_saas",
    pool_size=5,
    pool_reset_session=True,
    **db_config
)

# ─── SEGURIDAD: JWT y Bcrypt ──────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY no definida. Agrégala en las variables de entorno de Render.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 días

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


class TokenData(BaseModel):
    id_tienda: int
    id_usuario: int
    rol: str = "cajero"


class LoginRequest(BaseModel):
    username: str
    password: str


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

        rol: str = payload.get("rol", "cajero")

        # ─── MODIFICACIÓN QUIRÚRGICA ADAPTADA A TU MAIN.PY ───
        # Usamos tu db_pool existente para no agotar las conexiones
        conexion = db_pool.get_connection()
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("""
                            SELECT t.activa, u.id_usuario 
                            FROM tiendas t 
                            LEFT JOIN usuarios u ON u.id_usuario = %s AND u.activo = 1
                            WHERE t.id_tienda = %s
                        """, (id_usuario, id_tienda))
            estado = cursor.fetchone()

            if not estado or not estado['activa'] or not estado['id_usuario']:
                raise credentials_exception
        finally:
            cursor.close()
            conexion.close()
        # ─────────────────────────────────────────────────────

        return TokenData(id_tienda=id_tienda, id_usuario=id_usuario, rol=rol)
    except JWTError:
        raise credentials_exception

# ─── Modelos Operativos ───────────────────────────────────────────────────────
class TiposPermitidos(str, Enum):
    VENTA = "VENTA"
    RETIRO = "RETIRO"
    FONDO_CAJA = "FONDO_CAJA"
    COBRO_FIADO = "COBRO_FIADO"


class Movimiento(BaseModel):
    id_turno: int
    tipo_movimiento: TiposPermitidos
    producto: str = "Venta general"
    cantidad: float = Field(default=1.0, gt=0)
    precio_unitario: float = Field(gt=0)


class ActualizacionPrecio(BaseModel):
    nombre_producto: str
    nuevo_precio: float


class ProductoNuevo(BaseModel):
    codigo_barras: str | None = None
    nombre_producto: str
    precio_sugerido: float
    stock_actual: float = 0
    stock_minimo: float = 5
    proveedor: str | None = None
    fecha_caducidad: str | None = None
    unidad_medida: str = "pieza"


class ActualizacionProducto(BaseModel):
    nombre_producto: str
    precio_sugerido: float
    stock_actual: float
    stock_minimo: float
    proveedor: str | None = None
    codigo_barras: str | None = None
    fecha_caducidad: str | None = None
    unidad_medida: str = "pieza"


class EntradaMercancia(BaseModel):
    id_producto: int
    cantidad: float
    fecha_caducidad: str | None = None
    notas: str | None = None


class ResurtidoPorCodigo(BaseModel):
    codigo_barras: str
    cantidad: float
    fecha_caducidad: str | None = None


class ItemEntradaLote(BaseModel):
    id_producto: int
    cantidad: float
    fecha_caducidad: str | None = None


class EntradaLote(BaseModel):
    items: list[ItemEntradaLote]
    nota_general: str | None = None


class ClienteNuevo(BaseModel):
    nombre: str
    telefono: str | None = None


class ItemFiado(BaseModel):
    id_cuenta: int
    id_turno: int
    producto: str
    cantidad: float = 1.0
    precio: float


class AbonoFiado(BaseModel):
    id_cuenta: int
    id_turno: int
    monto: float = Field(gt=0)
    nota: str | None = None


class ItemVenta(BaseModel):
    producto: str
    cantidad: float = 1.0
    precio_unitario: float


class VentaLote(BaseModel):
    id_turno: int
    items: list[ItemVenta]


# ─── NUEVO MODELO: Merma (Prioridad 2B) ───────────────────────────────────────
class MermaProducto(BaseModel):
    id_producto: int
    cantidad: float = Field(gt=0)
    motivo: Literal["merma", "caducado", "uso_personal", "daño"] = "merma"
    nota: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────
def conectar_bd():
    return db_pool.get_connection()


# ─── NUEVO HELPER: Log de Auditoría (Prioridad 4A) ────────────────────────────
def _log(cursor, id_tienda: int, id_usuario: int, accion: str, detalle: str):
    cursor.execute(
        "INSERT INTO log_auditoria (id_tienda, id_usuario, accion, detalle) VALUES (%s, %s, %s, %s)",
        (id_tienda, id_usuario, accion, detalle)
    )


def _calcular_resumen(cursor, id_turno: int, id_tienda: int) -> dict:
    cursor.execute(
        "SELECT fecha_apertura, fecha_cierre FROM turnos WHERE id_turno = %s AND id_tienda = %s",
        (id_turno, id_tienda)
    )
    res = cursor.fetchone()
    fecha_apertura = res['fecha_apertura'] if res else None
    fecha_cierre = res['fecha_cierre'] if res else None

    # ── Leer reglas configuradas por la tienda ────────────────
    cursor.execute("SELECT config_resumen FROM tiendas WHERE id_tienda = %s", (id_tienda,))
    conf = cursor.fetchone()
    reglas = []
    if conf and conf['config_resumen']:
        try:
            reglas = json.loads(conf['config_resumen'])
        except Exception:
            pass

    cursor.execute("""
        SELECT
            SUM(CASE WHEN tipo_movimiento IN ('VENTA', 'FONDO_CAJA', 'COBRO_FIADO') THEN total_movimiento ELSE 0 END) AS ingresos,
            SUM(CASE WHEN tipo_movimiento = 'RETIRO' THEN total_movimiento ELSE 0 END) AS retiros
        FROM movimientos WHERE id_turno = %s AND id_tienda = %s
    """, (id_turno, id_tienda))
    res_total = cursor.fetchone()

    total_ingresos = float(res_total['ingresos']) if res_total and res_total['ingresos'] else 0.0
    total_retiros = float(res_total['retiros']) if res_total and res_total['retiros'] else 0.0
    total_en_caja = total_ingresos - total_retiros

    # ── Aplicar reglas dinámicas (claves + ids_productos) ─────
    resultados_reglas = {r['nombre']: 0.0 for r in reglas}
    total_deducciones = 0.0

    if reglas:
        cursor.execute("""
            SELECT m.producto, m.total_movimiento, p.id_producto
            FROM movimientos m
            LEFT JOIN productos p ON p.nombre_producto = m.producto AND p.id_tienda = m.id_tienda
            WHERE m.id_turno = %s AND m.id_tienda = %s AND m.tipo_movimiento = 'VENTA'
        """, (id_turno, id_tienda))
        ventas = cursor.fetchall()
        for v in ventas:
            prod_lower = (v['producto'] or "").lower()
            monto = float(v['total_movimiento'])
            id_prod = v['id_producto']
            for r in reglas:
                # Coincide por clave O por id_producto seleccionado
                claves = [k.strip().lower() for k in r.get('claves', '').split(',') if k.strip()]
                ids_sel = r.get('ids_productos', [])
                coincide_clave = any(clave in prod_lower for clave in claves)
                coincide_id = id_prod is not None and id_prod in ids_sel
                if coincide_clave or coincide_id:
                    resultados_reglas[r['nombre']] += monto
                    total_deducciones += monto
                    break  # evitar doble conteo

    return {
        "total_ingresos": total_ingresos,
        "total_retiros": total_retiros,
        "total_en_caja": total_en_caja,
        "reglas_resumen": resultados_reglas,
        "total_neto": total_en_caja - total_deducciones,
        "fecha_apertura": fecha_apertura,
        "fecha_cierre":   fecha_cierre,
    }


# ─── Auth Endpoint ────────────────────────────────────────────────────────────
@app.post("/login")
@limiter.limit("10/minute")
def login(request: Request, datos: LoginRequest):

    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
                    SELECT id_usuario, id_tienda, password_hash, rol 
                    FROM usuarios 
                    WHERE username = %s AND activo = 1
                """, (datos.username,)
        )
        user = cursor.fetchone()
        if not user or not pwd_context.verify(datos.password, user['password_hash']):
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        if user.get('rol') == 'superadmin':
            expire = datetime.utcnow() + timedelta(days=2)  # Admin dura estrictamente 2 días
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=ACCESS_TOKEN_EXPIRE_MINUTES)  # Cajero conserva sus 30 días
        # ────────────────────────────────────────────────────────────
        encoded_jwt = jwt.encode(
            {"id_tienda": user['id_tienda'], "id_usuario": user['id_usuario'],
             "rol": user.get('rol', 'cajero'), "exp": expire},
            SECRET_KEY, algorithm=ALGORITHM
        )
        return {"access_token": encoded_jwt, "token_type": "bearer", "rol": user.get('rol', 'cajero')}
    finally:
        cursor.close()
        conexion.close()


# ─── Endpoints Operativos ─────────────────────────────────────────────────────
@app.get("/despertar")
async def despertar():
    return {"estado": "despierto", "mensaje": "Servidor listo para el turno"}


@app.get("/")
def inicio():
    return {"mensaje": "API del Sistema de Caja SaaS funcionando"}


@app.get("/turno_actual")
def obtener_turno_actual(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id_turno, estado, fecha_apertura FROM turnos WHERE estado = 'ABIERTO' AND id_tienda = %s LIMIT 1",
                       (user.id_tienda,))
        turno = cursor.fetchone()
        return turno if turno else {"estado": "CERRADO"}
    finally:
        cursor.close()
        conexion.close()


@app.post("/abrir_turno")
def abrir_turno(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id_turno FROM turnos WHERE estado = 'ABIERTO' AND id_tienda = %s LIMIT 1",
                       (user.id_tienda,))
        existente = cursor.fetchone()
        if existente:
            return {"mensaje": "Ya hay un turno abierto", "id_turno": existente['id_turno']}
        cursor.execute("INSERT INTO turnos (estado, id_tienda) VALUES ('ABIERTO', %s)", (user.id_tienda,))
        conexion.commit()
        return {"mensaje": "Turno abierto con éxito", "id_turno": cursor.lastrowid}
    finally:
        cursor.close()
        conexion.close()


@app.post("/registrar_movimiento")
def registrar(mov: Movimiento, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        nombre_limpio = mov.producto.strip() if mov.producto else "Venta sin nombre"
        if mov.cantidad <= 0:
            mov.cantidad = 1.0
        # ── VALIDACIÓN ANTI-FUGA MULTI-TENANT ─────────────────────
        cursor.execute(
            "SELECT id_turno FROM turnos WHERE id_turno = %s AND id_tienda = %s AND estado = 'ABIERTO'",
            (mov.id_turno, user.id_tienda)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Turno no válido para esta tienda")
        # ──────────────────────────────────────────────────────────

        cursor.execute("""
            INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, precio_unitario, id_tienda)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (mov.id_turno, mov.tipo_movimiento, nombre_limpio, mov.cantidad, mov.precio_unitario, user.id_tienda))

        if mov.tipo_movimiento == 'VENTA' and nombre_limpio not in ("", "Venta sin nombre"):
            cursor.execute(
                "SELECT COUNT(*) FROM productos WHERE nombre_producto = %s AND id_tienda = %s",
                (nombre_limpio, user.id_tienda)
            )
            existe = cursor.fetchone()[0] > 0
            if not existe:
                cursor.execute(
                    "INSERT INTO productos (nombre_producto, precio_sugerido, activo, id_tienda) VALUES (%s, %s, 1, %s)",
                    (nombre_limpio, mov.precio_unitario, user.id_tienda)
                )
            else:
                cursor.execute("""
                    UPDATE productos
                    SET stock_actual = stock_actual - %s
                    WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
                """, (float(mov.cantidad), nombre_limpio, user.id_tienda))

        conexion.commit()
        return {"mensaje": "Registro guardado correctamente"}
    finally:
        cursor.close()
        conexion.close()


@app.delete("/borrar_movimiento/{id_movimiento}")
def borrar_movimiento(id_movimiento: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT tipo_movimiento, producto, cantidad FROM movimientos WHERE id_movimiento = %s AND id_tienda = %s",
            (id_movimiento, user.id_tienda)
        )
        mov = cursor.fetchone()
        if not mov:
            return {"mensaje": "Movimiento no encontrado"}
        cursor.execute("DELETE FROM movimientos WHERE id_movimiento = %s AND id_tienda = %s",
                       (id_movimiento, user.id_tienda))

        if mov["tipo_movimiento"] == "VENTA" and mov["producto"]:
            cursor.execute("""
                UPDATE productos
                SET stock_actual = stock_actual + %s
                WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
            """, (float(mov["cantidad"]), mov["producto"], user.id_tienda))

        # ─── LOG DE AUDITORÍA (Prioridad 4A) ──────────────────────
        _log(cursor, user.id_tienda, user.id_usuario, "BORRAR_MOVIMIENTO",
             f"id={id_movimiento} tipo={mov['tipo_movimiento']} producto={mov['producto']} cantidad={mov['cantidad']}")

        conexion.commit()
        return {"mensaje": "Movimiento cancelado"}
    finally:
        cursor.close()
        conexion.close()


@app.put("/actualizar_precio")
def actualizar_precio(datos: ActualizacionPrecio, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE productos SET precio_sugerido = %s WHERE nombre_producto = %s AND id_tienda = %s",
            (datos.nuevo_precio, datos.nombre_producto, user.id_tienda)
        )
        conexion.commit()
        if cursor.rowcount > 0:
            return {"mensaje": "Precio actualizado correctamente"}
        return {"mensaje": "No se encontró el producto en el catálogo"}
    finally:
        cursor.close()
        conexion.close()


@app.post("/corte_caja/{id_turno}")
def hacer_corte(id_turno: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "UPDATE turnos SET fecha_cierre = NOW(), estado = 'CERRADO' WHERE id_turno = %s AND id_tienda = %s",
            (id_turno, user.id_tienda)
        )
        resumen = _calcular_resumen(cursor, id_turno, user.id_tienda)  # calcula primero
        conexion.commit()                                               # cierra después, solo si no hubo error
        return resumen

    finally:
        cursor.close()
        conexion.close()


@app.get("/historial_turnos")
def historial_turnos(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_turno, fecha_apertura, fecha_cierre
            FROM turnos WHERE estado = 'CERRADO' AND id_tienda = %s
            ORDER BY fecha_apertura DESC LIMIT 30
        """, (user.id_tienda,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.get("/resumen_turno/{id_turno}")
def resumen_turno(id_turno: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        return _calcular_resumen(cursor, id_turno, user.id_tienda)
    finally:
        cursor.close()
        conexion.close()


@app.get("/movimientos_turno/{id_turno}")
def obtener_movimientos(id_turno: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_movimiento, cantidad, producto, total_movimiento, tipo_movimiento,
                   TIME_FORMAT(fecha_hora, '%H:%i') as hora
            FROM movimientos
            WHERE id_turno = %s AND id_tienda = %s
            ORDER BY id_movimiento DESC
        """, (id_turno, user.id_tienda))
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.get("/buscar_productos")
def buscar_productos(q: str = "", user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        if q == "":
            cursor.execute("""
                SELECT p.id_producto, p.nombre_producto, p.precio_sugerido, p.codigo_barras, p.unidad_medida
                FROM productos p
                LEFT JOIN (
                    SELECT producto, COUNT(*) as ventas FROM movimientos WHERE id_tienda = %s GROUP BY producto
                ) m ON p.nombre_producto = m.producto
                WHERE p.id_tienda = %s AND p.activo = 1
                ORDER BY m.ventas DESC LIMIT 15
            """, (user.id_tienda, user.id_tienda))
        else:
            cursor.execute(
                "SELECT id_producto, nombre_producto, precio_sugerido, codigo_barras, unidad_medida FROM productos WHERE nombre_producto LIKE %s AND activo = 1 AND id_tienda = %s LIMIT 10",
                (f"%{q}%", user.id_tienda)
            )
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.get("/productos")
def obtener_todos_productos(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_producto, nombre_producto, precio_sugerido, codigo_barras, unidad_medida FROM productos WHERE activo = 1 AND id_tienda = %s ORDER BY nombre_producto",
            (user.id_tienda,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.get("/producto_por_codigo/{codigo}")
def producto_por_codigo(codigo: str, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)

        # ── CAMINO VERDE: existe en la tienda ────────────────────────────────
        cursor.execute("""
            SELECT id_producto, nombre_producto, precio_sugerido,
                   stock_actual, stock_minimo, proveedor, fecha_caducidad,
                   codigo_barras, unidad_medida
            FROM productos WHERE codigo_barras = %s AND activo = 1 AND id_tienda = %s
        """, (codigo, user.id_tienda))
        producto = cursor.fetchone()
        if producto:
            return {"encontrado": True, "camino": "verde", "producto": producto}

        # ── CAMINO AMARILLO: existe en el catálogo global ────────────────────
        cursor.execute(
            "SELECT * FROM productos_globales WHERE codigo_barras = %s",
            (codigo,)
        )
        global_prod = cursor.fetchone()
        if global_prod:
            return {
                "encontrado": False,
                "camino": "amarillo",
                "sugerencia": {
                    "codigo_barras": global_prod["codigo_barras"],
                    "nombre_producto": global_prod["nombre_producto"],
                    "unidad_medida": global_prod["unidad_medida"]
                }
            }

        # ── CAMINO ROJO: no existe en ningún lado ────────────────────────────
        return {"encontrado": False, "camino": "rojo"}
    finally:
        cursor.close()
        conexion.close()


@app.post("/registrar_producto")
def registrar_producto(p: ProductoNuevo, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO productos
            (codigo_barras, nombre_producto, precio_sugerido,
             stock_actual, stock_minimo, proveedor, fecha_caducidad, activo, id_tienda, unidad_medida)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
        """, (p.codigo_barras or None, p.nombre_producto, p.precio_sugerido,
              p.stock_actual, p.stock_minimo, p.proveedor or None,
              p.fecha_caducidad or None, user.id_tienda, p.unidad_medida))

        # ─── CATÁLOGO GLOBAL: registrar si tiene código de barras (Prioridad 3) ──
        if p.codigo_barras:
            cursor.execute("""
                INSERT IGNORE INTO productos_globales (codigo_barras, nombre_producto, unidad_medida)
                VALUES (%s, %s, %s)
            """, (p.codigo_barras, p.nombre_producto, p.unidad_medida))

        conexion.commit()
        return {"mensaje": "Producto registrado", "id_producto": cursor.lastrowid}
    finally:
        cursor.close()
        conexion.close()


@app.put("/actualizar_producto/{id_producto}")
def actualizar_producto(id_producto: int, datos: ActualizacionProducto, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute("""
            UPDATE productos SET
                nombre_producto = %s,
                precio_sugerido = %s,
                stock_actual    = %s,
                stock_minimo    = %s,
                proveedor       = %s,
                codigo_barras   = %s,
                fecha_caducidad = %s,
                unidad_medida   = %s
            WHERE id_producto = %s AND activo = 1 AND id_tienda = %s
        """, (
            datos.nombre_producto, datos.precio_sugerido,
            datos.stock_actual, datos.stock_minimo,
            datos.proveedor or None, datos.codigo_barras or None,
            datos.fecha_caducidad or None, datos.unidad_medida, id_producto, user.id_tienda
        ))
        conexion.commit()
        if cursor.rowcount > 0:
            return {"mensaje": "Producto actualizado correctamente"}
        return {"mensaje": "No se encontró el producto"}
    finally:
        cursor.close()
        conexion.close()


@app.delete("/eliminar_producto/{id_producto}")
def eliminar_producto(id_producto: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE productos SET activo = 2 WHERE id_producto = %s AND id_tienda = %s",
            (id_producto, user.id_tienda)
        )
        conexion.commit()
        if cursor.rowcount > 0:
            return {"mensaje": "Producto eliminado del sistema (archivado)"}
        return {"mensaje": "No se encontró el producto o ya estaba inactivo"}
    finally:
        cursor.close()
        conexion.close()


@app.post("/entrada_mercancia")
def entrada_mercancia(e: EntradaMercancia, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE productos SET stock_actual = stock_actual + %s WHERE id_producto = %s AND id_tienda = %s",
            (e.cantidad, e.id_producto, user.id_tienda)
        )
        if e.fecha_caducidad:
            cursor.execute(
                "UPDATE productos SET fecha_caducidad = %s WHERE id_producto = %s AND id_tienda = %s",
                (e.fecha_caducidad, e.id_producto, user.id_tienda)
            )
        cursor.execute("""
            INSERT INTO entradas_mercancia (id_producto, cantidad, fecha_caducidad, notas, id_tienda)
            VALUES (%s, %s, %s, %s, %s)
        """, (e.id_producto, e.cantidad, e.fecha_caducidad or None, e.notas or None, user.id_tienda))
        conexion.commit()
        return {"mensaje": "Entrada registrada correctamente"}
    finally:
        cursor.close()
        conexion.close()


@app.post("/entrada_mercancia_lote")
def entrada_mercancia_lote(lote: EntradaLote, user: TokenData = Depends(get_current_user)):
    if not lote.items:
        return {"error": "El lote está vacío"}
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        for item in lote.items:
            cursor.execute(
                "UPDATE productos SET stock_actual = stock_actual + %s WHERE id_producto = %s AND id_tienda = %s",
                (item.cantidad, item.id_producto, user.id_tienda)
            )
            if item.fecha_caducidad:
                cursor.execute(
                    "UPDATE productos SET fecha_caducidad = %s WHERE id_producto = %s AND id_tienda = %s",
                    (item.fecha_caducidad, item.id_producto, user.id_tienda)
                )
            cursor.execute("""
                INSERT INTO entradas_mercancia (id_producto, cantidad, fecha_caducidad, notas, id_tienda)
                VALUES (%s, %s, %s, %s, %s)
            """, (
            item.id_producto, item.cantidad, item.fecha_caducidad or None, lote.nota_general or None, user.id_tienda))
        conexion.commit()
        return {"mensaje": f"Se registraron {len(lote.items)} productos correctamente"}
    finally:
        cursor.close()
        conexion.close()


@app.post("/resurtir_por_codigo")
def resurtir_por_codigo(r: ResurtidoPorCodigo, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_producto, nombre_producto FROM productos WHERE codigo_barras = %s AND activo = 1 AND id_tienda = %s",
            (r.codigo_barras, user.id_tienda)
        )
        producto = cursor.fetchone()
        if not producto:
            return {"encontrado": False, "mensaje": "Producto no encontrado"}
        cursor.execute(
            "UPDATE productos SET stock_actual = stock_actual + %s WHERE id_producto = %s AND id_tienda = %s",
            (r.cantidad, producto['id_producto'], user.id_tienda)
        )
        if r.fecha_caducidad:
            cursor.execute(
                "UPDATE productos SET fecha_caducidad = %s WHERE id_producto = %s AND id_tienda = %s",
                (r.fecha_caducidad, producto['id_producto'], user.id_tienda)
            )
        cursor.execute(
            "INSERT INTO entradas_mercancia (id_producto, cantidad, fecha_caducidad, id_tienda) VALUES (%s, %s, %s, %s)",
            (producto['id_producto'], r.cantidad, r.fecha_caducidad or None, user.id_tienda)
        )
        conexion.commit()
        return {"encontrado": True, "mensaje": f"Stock de {producto['nombre_producto']} actualizado"}
    finally:
        cursor.close()
        conexion.close()


@app.get("/inventario")
def listar_inventario(q: str = "", proveedor: str = "", user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        sql = """SELECT id_producto, codigo_barras, nombre_producto,
                        precio_sugerido, stock_actual, stock_minimo,
                        proveedor, fecha_caducidad, unidad_medida
                 FROM productos WHERE activo = 1 AND id_tienda = %s"""
        params = [user.id_tienda]
        if q:
            sql += " AND nombre_producto LIKE %s"
            params.append(f"%{q}%")
        if proveedor:
            sql += " AND proveedor = %s"
            params.append(proveedor)
        sql += " ORDER BY nombre_producto ASC"
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.get("/alertas")
def obtener_alertas(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_producto, codigo_barras, nombre_producto, stock_actual, stock_minimo, proveedor, fecha_caducidad,
                CASE 
                    WHEN stock_actual <= stock_minimo THEN 'STOCK_BAJO' 
                    WHEN fecha_caducidad IS NOT NULL AND fecha_caducidad <= DATE_ADD(NOW(), INTERVAL 7 DAY) THEN 'POR_CADUCAR' 
                    ELSE 'OK' 
                END as alerta 
            FROM productos 
            WHERE activo = 1 AND id_tienda = %s AND (
                stock_actual <= stock_minimo OR (fecha_caducidad IS NOT NULL AND fecha_caducidad <= DATE_ADD(NOW(), INTERVAL 7 DAY))
            )
            ORDER BY alerta DESC, fecha_caducidad
        """, (user.id_tienda,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.get("/proveedores")
def listar_proveedores(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT DISTINCT proveedor FROM productos WHERE proveedor IS NOT NULL AND activo = 1 AND id_tienda = %s ORDER BY proveedor",
            (user.id_tienda,)
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conexion.close()


@app.post("/descontar_stock/{id_producto}")
def descontar_stock(id_producto: int, cantidad: float = 1, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE productos SET stock_actual = stock_actual - %s WHERE id_producto = %s AND id_tienda = %s",
            (float(cantidad), id_producto, user.id_tienda)
        )
        conexion.commit()
        return {"mensaje": "Stock actualizado"}
    finally:
        cursor.close()
        conexion.close()


@app.get("/clientes")
def listar_clientes(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.id_cliente, c.nombre, c.telefono,
                   COALESCE(
                     (SELECT SUM(df.cantidad * df.precio)
                      FROM detalle_fiado df
                      JOIN cuentas_fiado cf ON df.id_cuenta = cf.id_cuenta
                      WHERE cf.id_cliente = c.id_cliente AND cf.estado = 'ABIERTA' AND df.id_tienda = %s)
                   , 0) -
                   COALESCE(
                     (SELECT SUM(a.monto)
                      FROM abonos a
                      JOIN cuentas_fiado cf ON a.id_cuenta = cf.id_cuenta
                      WHERE cf.id_cliente = c.id_cliente AND cf.estado = 'ABIERTA' AND a.id_tienda = %s)
                   , 0) AS saldo_actual
            FROM clientes c
            WHERE c.activo = 1 AND c.id_tienda = %s
            ORDER BY c.nombre ASC
        """, (user.id_tienda, user.id_tienda, user.id_tienda))
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.post("/clientes")
def crear_cliente(c: ClienteNuevo, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO clientes (nombre, telefono, id_tienda) VALUES (%s, %s, %s)",
            (c.nombre.strip(), c.telefono or None, user.id_tienda)
        )
        id_cliente = cursor.lastrowid
        cursor.execute(
            "INSERT INTO cuentas_fiado (id_cliente, id_tienda) VALUES (%s, %s)",
            (id_cliente, user.id_tienda)
        )
        conexion.commit()
        return {"mensaje": "Cliente registrado", "id_cliente": id_cliente}
    finally:
        cursor.close()
        conexion.close()


@app.delete("/clientes/{id_cliente}")
def eliminar_cliente(id_cliente: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT COALESCE(SUM(df.cantidad * df.precio), 0) - COALESCE(SUM(a.monto), 0) AS saldo
            FROM cuentas_fiado cf
            LEFT JOIN detalle_fiado df ON df.id_cuenta = cf.id_cuenta
            LEFT JOIN abonos a ON a.id_cuenta = cf.id_cuenta
            WHERE cf.id_cliente = %s AND cf.estado = 'ABIERTA' AND cf.id_tienda = %s
        """, (id_cliente, user.id_tienda))
        row = cursor.fetchone()
        if row and float(row["saldo"]) != 0:
            return {"error": f"El cliente tiene saldo pendiente de ${float(row['saldo']):.2f}. Salda la cuenta antes."}
        cursor.execute("UPDATE clientes SET activo = 0 WHERE id_cliente = %s AND id_tienda = %s",
                       (id_cliente, user.id_tienda))
        conexion.commit()
        return {"mensaje": "Cliente eliminado"}
    finally:
        cursor.close()
        conexion.close()


@app.get("/cuenta_fiado/{id_cliente}")
def obtener_cuenta(id_cliente: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_cliente, nombre, telefono FROM clientes WHERE id_cliente = %s AND activo = 1 AND id_tienda = %s",
            (id_cliente, user.id_tienda)
        )
        cliente = cursor.fetchone()
        if not cliente:
            return {"error": "Cliente no encontrado"}

        cursor.execute(
            "SELECT id_cuenta FROM cuentas_fiado WHERE id_cliente = %s AND estado = 'ABIERTA' AND id_tienda = %s LIMIT 1",
            (id_cliente, user.id_tienda)
        )
        cuenta = cursor.fetchone()
        if not cuenta:
            cursor.execute("INSERT INTO cuentas_fiado (id_cliente, id_tienda) VALUES (%s, %s)",
                           (id_cliente, user.id_tienda))
            conexion.commit()
            id_cuenta = cursor.lastrowid
        else:
            id_cuenta = cuenta['id_cuenta']

        cursor.execute("""
            SELECT producto, cantidad, precio, (cantidad * precio) AS subtotal,
                   DATE_FORMAT(fecha_hora, '%d/%m %H:%i') as fecha
            FROM detalle_fiado WHERE id_cuenta = %s AND id_tienda = %s
            ORDER BY fecha_hora ASC
        """, (id_cuenta, user.id_tienda))
        detalle = cursor.fetchall()

        cursor.execute("""
            SELECT monto, nota, DATE_FORMAT(fecha_hora, '%d/%m %H:%i') as fecha
            FROM abonos WHERE id_cuenta = %s AND id_tienda = %s
            ORDER BY fecha_hora ASC
        """, (id_cuenta, user.id_tienda))
        abonos = cursor.fetchall()

        total_fiado = sum(float(d['subtotal']) for d in detalle)
        total_abonos = sum(float(a['monto']) for a in abonos)
        saldo = total_fiado - total_abonos

        return {
            "cliente": cliente,
            "id_cuenta": id_cuenta,
            "detalle": detalle,
            "abonos": abonos,
            "total_fiado": total_fiado,
            "total_abonos": total_abonos,
            "saldo": saldo
        }
    finally:
        cursor.close()
        conexion.close()


@app.post("/agregar_fiado")
def agregar_fiado(item: ItemFiado, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()

        # ── VALIDACIÓN ANTI-FUGA MULTI-TENANT ─────────────────────
        cursor.execute("""
            SELECT cf.id_cuenta FROM cuentas_fiado cf
            JOIN clientes c ON c.id_cliente = cf.id_cliente
            WHERE cf.id_cuenta = %s AND c.id_tienda = %s AND cf.estado = 'ABIERTA'
        """, (item.id_cuenta, user.id_tienda))
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Cuenta de fiado no válida para esta tienda")
        # ──────────────────────────────────────────────────────────

        cursor.execute("""
            INSERT INTO detalle_fiado (id_cuenta, producto, cantidad, precio, id_tienda)
            VALUES (%s, %s, %s, %s, %s)
        """, (item.id_cuenta, item.producto.strip(), item.cantidad, item.precio, user.id_tienda))

        cursor.execute("""
            UPDATE productos SET stock_actual = stock_actual - %s
            WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
        """, (float(item.cantidad), item.producto.strip(), user.id_tienda))
        conexion.commit()
        return {"mensaje": "Fiado registrado correctamente"}
    finally:
        cursor.close()
        conexion.close()


@app.post("/registrar_abono")
def registrar_abono(abono: AbonoFiado, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)

        cursor.execute("""
            SELECT c.nombre FROM clientes c
            JOIN cuentas_fiado cf ON c.id_cliente = cf.id_cliente
            WHERE cf.id_cuenta = %s AND cf.id_tienda = %s
        """, (abono.id_cuenta, user.id_tienda))
        res = cursor.fetchone()
        if not res:
            raise HTTPException(status_code=403, detail="Cuenta de fiado no válida para esta tienda")
        nombre_cliente = res['nombre']

        # Validar que el turno pertenece a esta tienda
        cursor.execute(
            "SELECT id_turno FROM turnos WHERE id_turno = %s AND id_tienda = %s AND estado = 'ABIERTO'",
            (abono.id_turno, user.id_tienda)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Turno no válido para esta tienda")

        cursor.execute(
            "INSERT INTO abonos (id_cuenta, monto, nota, id_tienda) VALUES (%s, %s, %s, %s)",
            (abono.id_cuenta, abono.monto, abono.nota or None, user.id_tienda)
        )
        cursor.execute("""
            INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, precio_unitario, id_tienda)
            VALUES (%s, 'COBRO_FIADO', %s, 1, %s, %s)
        """, (abono.id_turno, f"Abono fiado — {nombre_cliente}", abono.monto, user.id_tienda))

        cursor.execute("""
            SELECT COALESCE(SUM(df.cantidad * df.precio), 0) AS total_fiado
            FROM detalle_fiado df WHERE df.id_cuenta = %s AND df.id_tienda = %s
        """, (abono.id_cuenta, user.id_tienda))
        tf = cursor.fetchone()

        cursor.execute(
            "SELECT COALESCE(SUM(monto), 0) AS total_abonos FROM abonos WHERE id_cuenta = %s AND id_tienda = %s",
            (abono.id_cuenta, user.id_tienda)
        )
        ta = cursor.fetchone()

        saldo_nuevo = float(tf['total_fiado']) - float(ta['total_abonos'])
        if saldo_nuevo == 0:
            cursor.execute(
                "UPDATE cuentas_fiado SET estado = 'SALDADA' WHERE id_cuenta = %s AND id_tienda = %s",
                (abono.id_cuenta, user.id_tienda)
            )
        conexion.commit()
        return {
            "mensaje": "Abono registrado",
            "saldo_restante": max(0, saldo_nuevo),
            "saldo_favor": abs(min(0, saldo_nuevo))  # 0 si pagó exacto, 30 si pagó de más
        }
    finally:
        cursor.close()
        conexion.close()


@app.post("/registrar_venta_lote")
def registrar_venta_lote(venta: VentaLote, user: TokenData = Depends(get_current_user)):
    if not venta.items:
        return {"error": "Sin items"}
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()

        # ── VALIDACIÓN ANTI-FUGA MULTI-TENANT ─────────────────────
        cursor.execute(
            "SELECT id_turno FROM turnos WHERE id_turno = %s AND id_tienda = %s AND estado = 'ABIERTO'",
            (venta.id_turno, user.id_tienda)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Turno no válido para esta tienda")
        # ──────────────────────────────────────────────────────────

        for i in venta.items:
            nombre_limpio = i.producto.strip() if i.producto else "Venta sin nombre"
            cursor.execute(
                "INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, precio_unitario, id_tienda) VALUES (%s, 'VENTA', %s, %s, %s, %s)",
                (venta.id_turno, nombre_limpio, i.cantidad, i.precio_unitario, user.id_tienda)
            )
            cursor.execute("SELECT COUNT(*) FROM productos WHERE nombre_producto = %s AND id_tienda = %s",
                           (nombre_limpio, user.id_tienda))
            existe = cursor.fetchone()[0] > 0
            if not existe:
                cursor.execute(
                    "INSERT INTO productos (nombre_producto, precio_sugerido, activo, id_tienda) VALUES (%s, %s, 1, %s)",
                    (nombre_limpio, i.precio_unitario, user.id_tienda)
                )
            else:
                cursor.execute("""
                    UPDATE productos
                    SET stock_actual = stock_actual - %s
                    WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
                """, (float(i.cantidad), nombre_limpio, user.id_tienda))
        conexion.commit()
        return {"ok": True, "registrados": len(venta.items)}
    finally:
        cursor.close()
        conexion.close()

class ReglaResumen(BaseModel):
    nombre: str
    claves: str
    ids_productos: List[int] = []

class ConfiguracionTicket(BaseModel):
    reglas: List[ReglaResumen] = []


@app.get("/configuracion_tienda")
def obtener_configuracion(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT config_resumen FROM tiendas WHERE id_tienda = %s", (user.id_tienda,))
        row = cursor.fetchone()
        reglas = json.loads(row['config_resumen']) if row and row['config_resumen'] else []
        return {"reglas": reglas}
    finally:
        cursor.close()
        conexion.close()


@app.put("/configuracion_tienda")
def actualizar_configuracion(config: ConfiguracionTicket, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        json_str = json.dumps([r.dict() for r in config.reglas])
        cursor.execute("UPDATE tiendas SET config_resumen = %s WHERE id_tienda = %s", (json_str, user.id_tienda))
        conexion.commit()
        return {"mensaje": "Configuración del ticket actualizada correctamente"}
    finally:
        cursor.close()
        conexion.close()


#proyecto caja rapida 1.0

# ─── NUEVO ENDPOINT: Historial de Entradas (Prioridad 2A) ─────────────────────
@app.get("/historial_entradas")
def historial_entradas(fecha: str = "", user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        sql = """
            SELECT e.id_entrada, p.nombre_producto, e.cantidad,
                   DATE_FORMAT(e.fecha_entrada, '%d/%m/%Y') AS fecha,
                   TIME_FORMAT(e.fecha_entrada, '%H:%i') AS hora,
                   e.notas, e.fecha_caducidad
            FROM entradas_mercancia e
            JOIN productos p ON p.id_producto = e.id_producto
            WHERE e.id_tienda = %s
        """
        params = [user.id_tienda]
        if fecha:
            sql += " AND DATE(e.fecha_entrada) = %s"
            params.append(fecha)
        sql += " ORDER BY e.fecha_entrada DESC LIMIT 200"
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


# ─── NUEVO ENDPOINT: Registrar Merma (Prioridad 2B) ───────────────────────────
@app.post("/registrar_merma")
def registrar_merma(m: MermaProducto, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT nombre_producto, stock_actual FROM productos WHERE id_producto = %s AND activo = 1 AND id_tienda = %s",
            (m.id_producto, user.id_tienda)
        )
        producto = cursor.fetchone()
        if not producto:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        cursor.execute(
            "UPDATE productos SET stock_actual = stock_actual - %s WHERE id_producto = %s AND id_tienda = %s",
            (m.cantidad, m.id_producto, user.id_tienda)
        )
        cursor.execute("""
            INSERT INTO entradas_mercancia (id_producto, cantidad, notas, id_tienda)
            VALUES (%s, %s, %s, %s)
        """, (m.id_producto, m.cantidad, f"[MERMA — {m.motivo}]", user.id_tienda))

        # ─── LOG DE AUDITORÍA ──────────────────────────────────────
        _log(cursor, user.id_tienda, user.id_usuario, "MERMA",
             f"producto_id={m.id_producto} cantidad={m.cantidad} motivo={m.motivo}")

        conexion.commit()
        return {"mensaje": f"Merma de {m.cantidad} unidades registrada para {producto['nombre_producto']}"}
    finally:
        cursor.close()
        conexion.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  PANEL SUPERADMIN — Endpoints existentes
#  Todos requieren rol='superadmin'. No modifican lógica existente.
# ═══════════════════════════════════════════════════════════════════════════════

def _require_superadmin(user: TokenData):
    """Helper: lanza 403 si el usuario no es superadmin."""
    if user.rol != "superadmin":
        raise HTTPException(status_code=403, detail="Acceso restringido al superadmin")


class TiendaNueva(BaseModel):
    nombre_comercial: str

class UsuarioNuevo(BaseModel):
    username: str
    password: str
    id_tienda: int
    rol: str = "cajero"

class ResetPassword(BaseModel):
    nuevo_password: str


# ── Tiendas ───────────────────────────────────────────────────────────────────

@app.get("/admin/tiendas")
def admin_listar_tiendas(user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.id_tienda, t.nombre_comercial, t.activa,
                   COUNT(DISTINCT u.id_usuario) AS total_usuarios,
                   (SELECT COUNT(*) FROM turnos tr WHERE tr.id_tienda = t.id_tienda
                    AND DATE(tr.fecha_apertura) = CURDATE()) AS turnos_hoy
            FROM tiendas t
            LEFT JOIN usuarios u ON u.id_tienda = t.id_tienda
            GROUP BY t.id_tienda
            ORDER BY t.id_tienda
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.post("/admin/tiendas")
def admin_crear_tienda(t: TiendaNueva, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    nombre = t.nombre_comercial.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO tiendas (nombre_comercial, activa) VALUES (%s, 1)", (nombre,)
        )
        conexion.commit()
        return {"mensaje": "Tienda creada", "id_tienda": cursor.lastrowid}
    finally:
        cursor.close()
        conexion.close()


@app.put("/admin/tiendas/{id_tienda}/activar")
def admin_activar_tienda(id_tienda: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute("UPDATE tiendas SET activa = 1 WHERE id_tienda = %s", (id_tienda,))
        conexion.commit()
        return {"mensaje": "Tienda activada"}
    finally:
        cursor.close()
        conexion.close()


@app.put("/admin/tiendas/{id_tienda}/desactivar")
def admin_desactivar_tienda(id_tienda: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute("UPDATE tiendas SET activa = 0 WHERE id_tienda = %s", (id_tienda,))
        # Cierre forzado de cualquier turno abierto en la tienda
        cursor.execute("""
            UPDATE turnos 
            SET estado = 'CERRADO', 
                fecha_cierre = CURRENT_TIMESTAMP 
            WHERE id_tienda = %s AND estado = 'ABIERTO'
        """, (id_tienda,))
        conexion.commit()
        return {"mensaje": "Tienda desactivada"}
    finally:
        cursor.close()
        conexion.close()


# ── Usuarios ──────────────────────────────────────────────────────────────────

@app.get("/admin/usuarios")
def admin_listar_usuarios(user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
                    SELECT u.id_usuario, u.username, u.rol, u.id_tienda, t.nombre_comercial
                    FROM usuarios u
                    JOIN tiendas t ON t.id_tienda = u.id_tienda
                    WHERE u.activo = 1
                    ORDER BY u.id_tienda, u.id_usuario
                """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.post("/admin/usuarios")
def admin_crear_usuario(u: UsuarioNuevo, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    username = u.username.strip()
    if not username or not u.password:
        raise HTTPException(status_code=400, detail="username y password son obligatorios")
    if u.rol not in ("superadmin", "cajero"):
        raise HTTPException(status_code=400, detail="rol inválido")
    hashed = pwd_context.hash(u.password)
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO usuarios (id_tienda, username, password_hash, rol) VALUES (%s, %s, %s, %s)",
            (u.id_tienda, username, hashed, u.rol)
        )
        conexion.commit()
        return {"mensaje": "Usuario creado", "id_usuario": cursor.lastrowid}
    except mysql.connector.IntegrityError:
        raise HTTPException(status_code=409, detail="El username ya existe")
    finally:
        cursor.close()
        conexion.close()


@app.put("/admin/usuarios/{id_usuario}/reset_password")
def admin_reset_password(id_usuario: int, datos: ResetPassword, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    if not datos.nuevo_password:
        raise HTTPException(status_code=400, detail="La contraseña no puede estar vacía")
    hashed = pwd_context.hash(datos.nuevo_password)
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s", (hashed, id_usuario)
        )
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return {"mensaje": "Contraseña actualizada"}
    finally:
        cursor.close()
        conexion.close()


# Reemplaza por completo tu función admin_eliminar_usuario con esta:
@app.delete("/admin/usuarios/{id_usuario}")
def admin_eliminar_usuario(id_usuario: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    if id_usuario == user.id_usuario:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        # CAMBIO QUIRÚRGICO: Soft-delete en lugar de borrado físico
        cursor.execute("UPDATE usuarios SET activo = 0 WHERE id_usuario = %s", (id_usuario,))
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return {"mensaje": "Usuario eliminado correctamente"}
    finally:
        cursor.close()
        conexion.close()

# ── Ventas del día por tienda ──────────────────────────────────────────────────

@app.get("/admin/ventas_hoy")
def admin_ventas_hoy(user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        # Sumamos los movimientos directamente desde el turno (igual que la caja)
        # sin importar la fecha calendario del movimiento
        cursor.execute("""
            SELECT 
                t.id_tienda, 
                t.nombre_comercial, 
                t.activa,
                COALESCE(SUM(CASE WHEN m.tipo_movimiento IN ('VENTA','FONDO_CAJA','COBRO_FIADO') 
                                  THEN m.total_movimiento ELSE 0 END), 0) AS ventas_hoy,
                COALESCE(SUM(CASE WHEN m.tipo_movimiento = 'RETIRO' 
                                  THEN m.total_movimiento ELSE 0 END), 0) AS retiros_hoy,
                COUNT(DISTINCT tr.id_turno) AS turnos_hoy
            FROM tiendas t

            -- 1. Buscamos los turnos de HOY o que sigan ABIERTOS (espejo del cajero)
            LEFT JOIN turnos tr ON t.id_tienda = tr.id_tienda 
                AND (DATE(tr.fecha_apertura) = CURDATE() OR tr.estado = 'ABIERTO')

            -- 2. Sumamos TODOS los movimientos de esos turnos exactos
            LEFT JOIN movimientos m ON m.id_turno = tr.id_turno

            GROUP BY t.id_tienda
            ORDER BY t.id_tienda
        """)

        rows = cursor.fetchall()
        for r in rows:
            r['neto_hoy'] = float(r['ventas_hoy']) - float(r['retiros_hoy'])
            r['ventas_hoy'] = float(r['ventas_hoy'])
            r['retiros_hoy'] = float(r['retiros_hoy'])

        return rows
    finally:
        cursor.close()
        conexion.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  PANEL SUPERADMIN v2 — 4 Módulos Nuevos
# ═══════════════════════════════════════════════════════════════════════════════

# ── MÓDULO 1: Edición (Update CRUD) ──────────────────────────────────────────

class ActualizacionNombreTienda(BaseModel):
    nombre_comercial: str

class ActualizacionUsuario(BaseModel):
    id_tienda: int
    rol: str


@app.put("/admin/tiendas/{id_tienda}/editar")
def admin_editar_tienda(id_tienda: int, datos: ActualizacionNombreTienda, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    nombre = datos.nombre_comercial.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE tiendas SET nombre_comercial = %s WHERE id_tienda = %s",
            (nombre, id_tienda)
        )
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Tienda no encontrada")
        return {"mensaje": "Nombre de tienda actualizado correctamente"}
    finally:
        cursor.close()
        conexion.close()


@app.put("/admin/usuarios/{id_usuario}/editar")
def admin_editar_usuario(id_usuario: int, datos: ActualizacionUsuario, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    if datos.rol not in ("superadmin", "cajero"):
        raise HTTPException(status_code=400, detail="rol inválido")
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        # Verificar que la tienda destino existe
        cursor.execute("SELECT id_tienda FROM tiendas WHERE id_tienda = %s", (datos.id_tienda,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="La tienda destino no existe")
        cursor.execute(
            "UPDATE usuarios SET id_tienda = %s, rol = %s WHERE id_usuario = %s AND activo = 1",
            (datos.id_tienda, datos.rol, id_usuario)
        )
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return {"mensaje": "Usuario actualizado correctamente"}
    finally:
        cursor.close()
        conexion.close()


# ── MÓDULO 2: Máquina del Tiempo (Filtro de Fechas) ──────────────────────────

@app.get("/admin/ventas_reporte")
def admin_ventas_reporte(
    fecha_inicio: str,
    fecha_fin: str,
    user: TokenData = Depends(get_current_user)
):
    _require_superadmin(user)
    # Validación básica de formato de fechas
    try:
        datetime.strptime(fecha_inicio, "%Y-%m-%d")
        datetime.strptime(fecha_fin, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use YYYY-MM-DD")

    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                t.id_tienda,
                t.nombre_comercial,
                t.activa,
                COALESCE(SUM(CASE WHEN m.tipo_movimiento IN ('VENTA','FONDO_CAJA','COBRO_FIADO')
                                  THEN m.total_movimiento ELSE 0 END), 0) AS total_ventas,
                COALESCE(SUM(CASE WHEN m.tipo_movimiento = 'RETIRO'
                                  THEN m.total_movimiento ELSE 0 END), 0) AS total_retiros,
                COUNT(DISTINCT tr.id_turno) AS total_turnos
            FROM tiendas t
            LEFT JOIN turnos tr ON t.id_tienda = tr.id_tienda
                AND DATE(tr.fecha_apertura) BETWEEN %s AND %s
            LEFT JOIN movimientos m ON m.id_turno = tr.id_turno
            GROUP BY t.id_tienda
            ORDER BY t.id_tienda
        """, (fecha_inicio, fecha_fin))

        rows = cursor.fetchall()
        for r in rows:
            r['total_ventas'] = float(r['total_ventas'])
            r['total_retiros'] = float(r['total_retiros'])
            r['total_neto'] = r['total_ventas'] - r['total_retiros']

        return {
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "tiendas": rows
        }
    finally:
        cursor.close()
        conexion.close()


# ── MÓDULO 3: Control de Suscripciones (Pagos) ───────────────────────────────

class SuscripcionTienda(BaseModel):
    dia_corte: int
    monto_mensual: float
    estado_pago: str


@app.get("/admin/tiendas/{id_tienda}/suscripcion")
def admin_obtener_suscripcion(id_tienda: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_tienda, nombre_comercial, dia_corte, monto_mensual, estado_pago FROM tiendas WHERE id_tienda = %s",
            (id_tienda,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tienda no encontrada")
        row['monto_mensual'] = float(row['monto_mensual'])
        return row
    finally:
        cursor.close()
        conexion.close()


@app.put("/admin/tiendas/{id_tienda}/suscripcion")
def admin_actualizar_suscripcion(id_tienda: int, datos: SuscripcionTienda, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    if datos.estado_pago not in ("AL_DIA", "ATRASADO"):
        raise HTTPException(status_code=400, detail="estado_pago inválido. Use AL_DIA o ATRASADO")
    if not (1 <= datos.dia_corte <= 31):
        raise HTTPException(status_code=400, detail="dia_corte debe ser un número entre 1 y 31")
    if datos.monto_mensual < 0:
        raise HTTPException(status_code=400, detail="monto_mensual no puede ser negativo")
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE tiendas SET dia_corte = %s, monto_mensual = %s, estado_pago = %s WHERE id_tienda = %s",
            (datos.dia_corte, datos.monto_mensual, datos.estado_pago, id_tienda)
        )
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Tienda no encontrada")
        return {"mensaje": "Suscripción actualizada correctamente"}
    finally:
        cursor.close()
        conexion.close()


# ── MÓDULO 4: Modo "Dios" (Soporte Técnico) ───────────────────────────────────

@app.get("/admin/tienda/{id_tienda}/inventario")
def admin_inventario_tienda(id_tienda: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        # Verificar que la tienda existe
        cursor.execute("SELECT nombre_comercial FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        tienda = cursor.fetchone()
        if not tienda:
            raise HTTPException(status_code=404, detail="Tienda no encontrada")
        cursor.execute("""
            SELECT id_producto, codigo_barras, nombre_producto,
                   precio_sugerido, stock_actual, stock_minimo,
                   proveedor, fecha_caducidad, unidad_medida
            FROM productos
            WHERE activo = 1 AND id_tienda = %s
            ORDER BY nombre_producto ASC
        """, (id_tienda,))
        productos = cursor.fetchall()
        return {
            "id_tienda": id_tienda,
            "nombre_comercial": tienda['nombre_comercial'],
            "total_productos": len(productos),
            "productos": productos
        }
    finally:
        cursor.close()
        conexion.close()


# ─── NUEVO ENDPOINT: Log de Auditoría para Superadmin (Prioridad 4A) ──────────
@app.get("/admin/log_auditoria/{id_tienda}")
def admin_log_auditoria(id_tienda: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT l.id_log, u.username, l.accion, l.detalle,
                   DATE_FORMAT(l.fecha_hora, '%d/%m/%Y %H:%i') AS fecha_hora
            FROM log_auditoria l
            JOIN usuarios u ON u.id_usuario = l.id_usuario
            WHERE l.id_tienda = %s
            ORDER BY l.fecha_hora DESC LIMIT 100
        """, (id_tienda,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()