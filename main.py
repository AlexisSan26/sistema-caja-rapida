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

class ProductoNuevo(BaseModel):
    codigo_barras: str = None
    nombre_producto: str
    precio_sugerido: float
    stock_actual: int = 0
    stock_minimo: int = 5
    proveedor: str = None
    fecha_caducidad: str = None

class EntradaMercancia(BaseModel):
    id_producto: int
    cantidad: int
    fecha_caducidad: str = None
    notas: str = None

class ResurtidoPorCodigo(BaseModel):
    codigo_barras: str
    cantidad: int
    fecha_caducidad: str = None


# ─── Helpers ─────────────────────────────────────────────────────────────────
def conectar_bd():
    conexion = mysql.connector.connect(**db_config)
    cursor = conexion.cursor()
    cursor.execute("SET time_zone = '-06:00';")
    cursor.close()
    return conexion


def _calcular_resumen(cursor, id_turno: int) -> dict:
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


# ─── Endpoints existentes ─────────────────────────────────────────────────────
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

        # ── Inserta el movimiento en su tabla correspondiente ──────────────
        cursor.execute("""
            INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, precio_unitario)
            VALUES (%s, %s, %s, %s, %s)
        """, (mov.id_turno, mov.tipo_movimiento, nombre_limpio, mov.cantidad, mov.precio_unitario))

        # ── Solo agrega al catálogo si es VENTA y el producto NO existe aún ─
        # No inserta si ya está en el catálogo — el catálogo se gestiona desde Inventario
        if mov.tipo_movimiento == 'VENTA' and nombre_limpio not in ("", "Venta sin nombre"):
            cursor.execute(
                "SELECT COUNT(*) FROM productos WHERE nombre_producto = %s",
                (nombre_limpio,)
            )
            existe = cursor.fetchone()[0] > 0
            if not existe:
                cursor.execute(
                    "INSERT INTO productos (nombre_producto, precio_sugerido, activo) VALUES (%s, %s, 1)",
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
                "SELECT nombre_producto, precio_sugerido FROM productos WHERE nombre_producto LIKE %s AND activo = 1 LIMIT 10",
                (f"%{q}%",)
            )
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()


# ─── Endpoints de inventario ──────────────────────────────────────────────────

@app.get("/producto_por_codigo/{codigo}")
def producto_por_codigo(codigo: str):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_producto, nombre_producto, precio_sugerido,
                   stock_actual, stock_minimo, proveedor, fecha_caducidad
            FROM productos WHERE codigo_barras = %s AND activo = 1
        """, (codigo,))
        producto = cursor.fetchone()
        if producto:
            return {"encontrado": True, "producto": producto}
        return {"encontrado": False}
    finally:
        cursor.close()
        conexion.close()

@app.post("/registrar_producto")
def registrar_producto(p: ProductoNuevo):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO productos
            (codigo_barras, nombre_producto, precio_sugerido,
             stock_actual, stock_minimo, proveedor, fecha_caducidad, activo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
        """, (p.codigo_barras or None, p.nombre_producto, p.precio_sugerido,
              p.stock_actual, p.stock_minimo, p.proveedor or None,
              p.fecha_caducidad or None))
        conexion.commit()
        return {"mensaje": "Producto registrado", "id_producto": cursor.lastrowid}
    finally:
        cursor.close()
        conexion.close()

@app.post("/entrada_mercancia")
def entrada_mercancia(e: EntradaMercancia):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE productos SET stock_actual = stock_actual + %s WHERE id_producto = %s",
            (e.cantidad, e.id_producto)
        )
        if e.fecha_caducidad:
            cursor.execute(
                "UPDATE productos SET fecha_caducidad = %s WHERE id_producto = %s",
                (e.fecha_caducidad, e.id_producto)
            )
        cursor.execute("""
            INSERT INTO entradas_mercancia (id_producto, cantidad, fecha_caducidad, notas)
            VALUES (%s, %s, %s, %s)
        """, (e.id_producto, e.cantidad, e.fecha_caducidad or None, e.notas or None))
        conexion.commit()
        return {"mensaje": "Entrada registrada correctamente"}
    finally:
        cursor.close()
        conexion.close()

@app.post("/resurtir_por_codigo")
def resurtir_por_codigo(r: ResurtidoPorCodigo):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_producto, nombre_producto FROM productos WHERE codigo_barras = %s AND activo = 1",
            (r.codigo_barras,)
        )
        producto = cursor.fetchone()
        if not producto:
            return {"encontrado": False, "mensaje": "Producto no encontrado"}
        cursor.execute(
            "UPDATE productos SET stock_actual = stock_actual + %s WHERE id_producto = %s",
            (r.cantidad, producto['id_producto'])
        )
        if r.fecha_caducidad:
            cursor.execute(
                "UPDATE productos SET fecha_caducidad = %s WHERE id_producto = %s",
                (r.fecha_caducidad, producto['id_producto'])
            )
        cursor.execute(
            "INSERT INTO entradas_mercancia (id_producto, cantidad, fecha_caducidad) VALUES (%s, %s, %s)",
            (producto['id_producto'], r.cantidad, r.fecha_caducidad or None)
        )
        conexion.commit()
        return {"encontrado": True, "mensaje": f"Stock de {producto['nombre_producto']} actualizado"}
    finally:
        cursor.close()
        conexion.close()

@app.get("/inventario")
def listar_inventario(q: str = "", proveedor: str = ""):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        sql = """SELECT id_producto, codigo_barras, nombre_producto,
                        precio_sugerido, stock_actual, stock_minimo,
                        proveedor, fecha_caducidad
                 FROM productos WHERE activo = 1"""
        params = []
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
def obtener_alertas():
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT * FROM v_alertas")
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()

@app.get("/proveedores")
def listar_proveedores():
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT DISTINCT proveedor FROM productos WHERE proveedor IS NOT NULL AND activo = 1 ORDER BY proveedor"
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conexion.close()

@app.post("/descontar_stock/{id_producto}")
def descontar_stock(id_producto: int, cantidad: float = 1):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE productos SET stock_actual = GREATEST(0, stock_actual - %s) WHERE id_producto = %s",
            (int(cantidad), id_producto)
        )
        conexion.commit()
        return {"mensaje": "Stock actualizado"}
    finally:
        cursor.close()
        conexion.close()