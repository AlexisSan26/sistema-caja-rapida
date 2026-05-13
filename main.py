import os
from fastapi import FastAPI, Depends, HTTPException, status
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

}

# ─── RENDIMIENTO: Pool de conexiones a 8 ──────────────────────────────────────
db_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="cajapool_saas",
    pool_size=8,
    pool_reset_session=True,
    **db_config
)

# ─── SEGURIDAD: JWT y Bcrypt ──────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_key_caja_rapida_saas")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 días

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


class TokenData(BaseModel):
    id_tienda: int
    id_usuario: int


class LoginRequest(BaseModel):
    username: str
    password: str


def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o token expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id_tienda: int = payload.get("id_tienda")
        id_usuario: int = payload.get("id_usuario")
        if id_tienda is None or id_usuario is None:
            raise credentials_exception
        return TokenData(id_tienda=id_tienda, id_usuario=id_usuario)
    except JWTError:
        raise credentials_exception


# ─── Modelos Operativos ───────────────────────────────────────────────────────
class TiposPermitidos(str, Enum):
    VENTA = "VENTA"
    FIADO = "FIADO"
    RETIRO = "RETIRO"
    FONDO_CAJA = "FONDO_CAJA"
    COBRO_FIADO = "COBRO_FIADO"


class Movimiento(BaseModel):
    id_turno: int
    tipo_movimiento: TiposPermitidos
    producto: str = "Venta general"
    cantidad: float = 1.0
    precio_unitario: float


class ActualizacionPrecio(BaseModel):
    nombre_producto: str
    nuevo_precio: float


class ProductoNuevo(BaseModel):
    codigo_barras: str | None = None
    nombre_producto: str
    precio_sugerido: float
    stock_actual: int = 0
    stock_minimo: int = 5
    proveedor: str | None = None
    fecha_caducidad: str | None = None


class ActualizacionProducto(BaseModel):
    nombre_producto: str
    precio_sugerido: float
    stock_actual: int
    stock_minimo: int
    proveedor: str | None = None
    codigo_barras: str | None = None
    fecha_caducidad: str | None = None


class EntradaMercancia(BaseModel):
    id_producto: int
    cantidad: int
    fecha_caducidad: str | None = None
    notas: str | None = None


class ResurtidoPorCodigo(BaseModel):
    codigo_barras: str
    cantidad: int
    fecha_caducidad: str | None = None


class ItemEntradaLote(BaseModel):
    id_producto: int
    cantidad: int
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
    monto: float
    nota: str | None = None


class ItemVenta(BaseModel):
    producto: str
    cantidad: float = 1.0
    precio_unitario: float


class VentaLote(BaseModel):
    id_turno: int
    items: list[ItemVenta]


# ─── Helpers ──────────────────────────────────────────────────────────────────
def conectar_bd():
    conexion = db_pool.get_connection()
    cursor = conexion.cursor()
    cursor.execute("SET time_zone = '-06:00';")
    cursor.close()
    return conexion


def _calcular_resumen(cursor, id_turno: int, id_tienda: int) -> dict:
    cursor.execute(
        "SELECT fecha_apertura FROM turnos WHERE id_turno = %s AND id_tienda = %s",
        (id_turno, id_tienda)
    )
    res = cursor.fetchone()
    fecha_apertura = res['fecha_apertura'] if res else None

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

    cursor.execute("""
        SELECT SUM(total_movimiento) AS total_c
        FROM movimientos
        WHERE id_turno = %s AND id_tienda = %s AND tipo_movimiento = 'VENTA'
        AND (producto LIKE '%cigarro%' OR producto LIKE '%time%')
    """, (id_turno, id_tienda))
    res_c = cursor.fetchone()
    total_cigarros = float(res_c['total_c']) if res_c and res_c['total_c'] else 0.0

    cursor.execute("""
        SELECT SUM(total_movimiento) AS total_h
        FROM movimientos
        WHERE id_turno = %s AND id_tienda = %s AND tipo_movimiento = 'VENTA'
        AND producto LIKE '%helado%'
    """, (id_turno, id_tienda))
    res_h = cursor.fetchone()
    total_helados = float(res_h['total_h']) if res_h and res_h['total_h'] else 0.0

    return {
        "total_ingresos": total_ingresos,
        "total_retiros": total_retiros,
        "total_en_caja": total_en_caja,
        "total_cigarros_time": total_cigarros,
        "total_helados": total_helados,
        "total_neto": total_en_caja - total_cigarros - total_helados,
        "fecha_apertura": fecha_apertura,
    }


# ─── Auth Endpoint ────────────────────────────────────────────────────────────
@app.post("/login")
def login(datos: LoginRequest):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_usuario, id_tienda, password_hash FROM usuarios WHERE username = %s",
            (datos.username,)
        )
        user = cursor.fetchone()
        if not user or not pwd_context.verify(datos.password, user['password_hash']):
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        encoded_jwt = jwt.encode(
            {"id_tienda": user['id_tienda'], "id_usuario": user['id_usuario'], "exp": expire},
            SECRET_KEY, algorithm=ALGORITHM
        )
        return {"access_token": encoded_jwt, "token_type": "bearer"}
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
        cursor.execute("SELECT id_turno, estado FROM turnos WHERE estado = 'ABIERTO' AND id_tienda = %s LIMIT 1",
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
                """, (int(mov.cantidad), nombre_limpio, user.id_tienda))

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
            """, (int(mov["cantidad"]), mov["producto"], user.id_tienda))
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
        conexion.commit()
        return _calcular_resumen(cursor, id_turno, user.id_tienda)
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
            ORDER BY id_turno DESC LIMIT 30
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
                SELECT p.nombre_producto, p.precio_sugerido
                FROM productos p
                LEFT JOIN (
                    SELECT producto, COUNT(*) as ventas FROM movimientos WHERE id_tienda = %s GROUP BY producto
                ) m ON p.nombre_producto = m.producto
                WHERE p.id_tienda = %s AND p.activo = 1
                ORDER BY m.ventas DESC LIMIT 15
            """, (user.id_tienda, user.id_tienda))
        else:
            cursor.execute(
                "SELECT nombre_producto, precio_sugerido FROM productos WHERE nombre_producto LIKE %s AND activo = 1 AND id_tienda = %s LIMIT 10",
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
            "SELECT nombre_producto, precio_sugerido, codigo_barras FROM productos WHERE activo = 1 AND id_tienda = %s ORDER BY nombre_producto",
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
        cursor.execute("""
            SELECT id_producto, nombre_producto, precio_sugerido,
                   stock_actual, stock_minimo, proveedor, fecha_caducidad, codigo_barras
            FROM productos WHERE codigo_barras = %s AND activo = 1 AND id_tienda = %s
        """, (codigo, user.id_tienda))
        producto = cursor.fetchone()
        if producto:
            return {"encontrado": True, "producto": producto}
        return {"encontrado": False}
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
             stock_actual, stock_minimo, proveedor, fecha_caducidad, activo, id_tienda)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)
        """, (p.codigo_barras or None, p.nombre_producto, p.precio_sugerido,
              p.stock_actual, p.stock_minimo, p.proveedor or None,
              p.fecha_caducidad or None, user.id_tienda))
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
                fecha_caducidad = %s
            WHERE id_producto = %s AND activo = 1 AND id_tienda = %s
        """, (
            datos.nombre_producto, datos.precio_sugerido,
            datos.stock_actual, datos.stock_minimo,
            datos.proveedor or None, datos.codigo_barras or None,
            datos.fecha_caducidad or None, id_producto, user.id_tienda
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
                        proveedor, fecha_caducidad
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
            (int(cantidad), id_producto, user.id_tienda)
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
        if row and float(row["saldo"]) > 0:
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
        cursor.execute("""
            INSERT INTO detalle_fiado (id_cuenta, producto, cantidad, precio, id_tienda)
            VALUES (%s, %s, %s, %s, %s)
        """, (item.id_cuenta, item.producto.strip(), item.cantidad, item.precio, user.id_tienda))

        cursor.execute("""
            UPDATE productos SET stock_actual = stock_actual - %s
            WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
        """, (int(item.cantidad), item.producto.strip(), user.id_tienda))
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
        nombre_cliente = res['nombre'] if res else "Cliente"

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
        if saldo_nuevo <= 0:
            cursor.execute(
                "UPDATE cuentas_fiado SET estado = 'SALDADA' WHERE id_cuenta = %s AND id_tienda = %s",
                (abono.id_cuenta, user.id_tienda)
            )
        conexion.commit()
        return {"mensaje": "Abono registrado", "saldo_restante": max(0, saldo_nuevo)}
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
                """, (int(i.cantidad), nombre_limpio, user.id_tienda))
        conexion.commit()
        return {"ok": True, "registrados": len(venta.items)}
    finally:
        cursor.close()
        conexion.close()