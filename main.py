import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Configuración desde variables de entorno ───────────────────────────────
# Crea un archivo .env en la misma carpeta con estas claves (NO lo subas a GitHub):
#   DB_HOST=mysql-345b06e4-...
#   DB_PORT=28257
#   DB_USER=avnadmin
#   DB_PASSWORD=tu_password_aqui
#   DB_NAME=defaultdb
db_config = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 28257)),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
}


# ─── Modelos ─────────────────────────────────────────────────────────────────
class Movimiento(BaseModel):
    id_turno: int
    tipo_movimiento: str
    producto: str = "Venta general"
    cantidad: float = 1.0
    precio_unitario: float


class ActualizacionPrecio(BaseModel):
    nombre_producto: str
    nuevo_precio: float


# ─── Helpers ─────────────────────────────────────────────────────────────────
def conectar_bd():
    conexion = mysql.connector.connect(**db_config)
    cursor = conexion.cursor()
    cursor.execute("SET time_zone = '-06:00';")
    cursor.close()
    return conexion


def _calcular_resumen(cursor, id_turno: int) -> dict:
    """Lógica compartida entre resumen_turno y corte_caja."""
    cursor.execute(
        "SELECT fecha_apertura FROM turnos WHERE id_turno = %s", (id_turno,)
    )
    res = cursor.fetchone()
    fecha_apertura = res['fecha_apertura'] if res else None

    cursor.execute("""
        SELECT
            SUM(CASE WHEN tipo_movimiento IN ('VENTA', 'FONDO_CAJA') THEN total_movimiento ELSE 0 END) -
            SUM(CASE WHEN tipo_movimiento = 'RETIRO' THEN total_movimiento ELSE 0 END) AS total_en_caja
        FROM movimientos WHERE id_turno = %s
    """, (id_turno,))
    res_total = cursor.fetchone()
    total_en_caja = float(res_total['total_en_caja']) if res_total and res_total['total_en_caja'] else 0.0

    cursor.execute("""
        SELECT SUM(total_movimiento) AS total_c
        FROM movimientos
        WHERE id_turno = %s AND tipo_movimiento = 'VENTA'
        AND (producto LIKE '%cigarro%' OR producto LIKE '%time%')
    """, (id_turno,))
    res_c = cursor.fetchone()
    total_cigarros = float(res_c['total_c']) if res_c and res_c['total_c'] else 0.0

    cursor.execute("""
        SELECT SUM(total_movimiento) AS total_h
        FROM movimientos
        WHERE id_turno = %s AND tipo_movimiento = 'VENTA'
        AND producto LIKE '%helado%'
    """, (id_turno,))
    res_h = cursor.fetchone()
    total_helados = float(res_h['total_h']) if res_h and res_h['total_h'] else 0.0

    return {
        "total_en_caja": total_en_caja,
        "total_cigarros_time": total_cigarros,
        "total_helados": total_helados,
        "total_neto": total_en_caja - total_cigarros - total_helados,
        "fecha_apertura": fecha_apertura,
    }


# ─── Endpoints ───────────────────────────────────────────────────────────────
@app.get("/despertar")
async def despertar():
    return {"estado": "despierto", "mensaje": "Servidor listo para el turno"}


@app.get("/")
def inicio():
    return {"mensaje": "API del Sistema de Caja funcionando al 100%"}


@app.get("/turno_actual")
def obtener_turno_actual():
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id_turno, estado FROM turnos WHERE estado = 'ABIERTO' LIMIT 1")
        turno = cursor.fetchone()
        return turno if turno else {"estado": "CERRADO"}
    finally:
        cursor.close()
        conexion.close()


@app.post("/abrir_turno")
def abrir_turno():
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id_turno FROM turnos WHERE estado = 'ABIERTO' LIMIT 1")
        existente = cursor.fetchone()
        if existente:
            return {"mensaje": "Ya hay un turno abierto", "id_turno": existente['id_turno']}

        cursor.execute("INSERT INTO turnos (estado) VALUES ('ABIERTO')")
        conexion.commit()
        return {"mensaje": "Turno abierto con éxito", "id_turno": cursor.lastrowid}
    finally:
        cursor.close()
        conexion.close()


@app.post("/registrar_movimiento")
def registrar(mov: Movimiento):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        nombre_limpio = mov.producto.strip() if mov.producto else "Venta sin nombre"
        if mov.cantidad <= 0:
            mov.cantidad = 1.0

        cursor.execute("""
            INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, precio_unitario)
            VALUES (%s, %s, %s, %s, %s)
        """, (mov.id_turno, mov.tipo_movimiento, nombre_limpio, mov.cantidad, mov.precio_unitario))

        if mov.tipo_movimiento == 'VENTA' and nombre_limpio not in ("", "Venta sin nombre"):
            cursor.execute(
                "INSERT IGNORE INTO productos (nombre_producto, precio_sugerido) VALUES (%s, %s)",
                (nombre_limpio, mov.precio_unitario)
            )

        conexion.commit()
        return {"mensaje": "Registro guardado correctamente"}
    finally:
        cursor.close()
        conexion.close()


@app.delete("/borrar_movimiento/{id_movimiento}")
def borrar_movimiento(id_movimiento: int):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute("DELETE FROM movimientos WHERE id_movimiento = %s", (id_movimiento,))
        conexion.commit()
        return {"mensaje": "Movimiento cancelado"}
    finally:
        cursor.close()
        conexion.close()


@app.put("/actualizar_precio")
def actualizar_precio(datos: ActualizacionPrecio):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE productos SET precio_sugerido = %s WHERE nombre_producto = %s",
            (datos.nuevo_precio, datos.nombre_producto)
        )
        conexion.commit()
        if cursor.rowcount > 0:
            return {"mensaje": "Precio actualizado correctamente"}
        return {"mensaje": "No se encontró el producto en el catálogo"}
    finally:
        cursor.close()
        conexion.close()


# POST en lugar de GET — un corte cierra el turno, eso es una acción, no una consulta
@app.post("/corte_caja/{id_turno}")
def hacer_corte(id_turno: int):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "UPDATE turnos SET fecha_cierre = NOW(), estado = 'CERRADO' WHERE id_turno = %s",
            (id_turno,)
        )
        conexion.commit()
        return _calcular_resumen(cursor, id_turno)
    finally:
        cursor.close()
        conexion.close()


@app.get("/historial_turnos")
def historial_turnos():
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_turno, fecha_apertura, fecha_cierre
            FROM turnos WHERE estado = 'CERRADO'
            ORDER BY id_turno DESC LIMIT 30
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.get("/resumen_turno/{id_turno}")
def resumen_turno(id_turno: int):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        return _calcular_resumen(cursor, id_turno)
    finally:
        cursor.close()
        conexion.close()


@app.get("/movimientos_turno/{id_turno}")
def obtener_movimientos(id_turno: int):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_movimiento, cantidad, producto, total_movimiento, tipo_movimiento,
                   TIME_FORMAT(fecha_hora, '%H:%i') as hora
            FROM movimientos
            WHERE id_turno = %s
            ORDER BY id_movimiento DESC
        """, (id_turno,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


@app.get("/buscar_productos")
def buscar_productos(q: str = ""):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        if q == "":
            cursor.execute("""
                SELECT p.nombre_producto, p.precio_sugerido
                FROM productos p
                LEFT JOIN (
                    SELECT producto, COUNT(*) as ventas FROM movimientos GROUP BY producto
                ) m ON p.nombre_producto = m.producto
                ORDER BY m.ventas DESC LIMIT 15
            """)
        else:
            cursor.execute(
                "SELECT nombre_producto, precio_sugerido FROM productos WHERE nombre_producto LIKE %s LIMIT 10",
                (f"%{q}%",)
            )
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()