from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import mysql.connector


app = FastAPI()

# Configuración de CORS para que tu GitHub Pages pueda conectarse
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ruta para el despertador automático de las 8:50 AM
@app.get("/despertar")
async def despertar():
    return {"estado": "despierto", "mensaje": "Servidor listo para el turno"}

# --- AQUÍ EMPIEZA TU CÓDIGO ACTUAL ---
# Asegúrate de NO borrar tus rutas de @app.post("/abrir-caja") o @app.get("/ventas")


db_config = {
    'host': 'mysql-345b06e4-proyectotiendarapida26.d.aivencloud.com',
    'port': 28257,
    'user': 'avnadmin',
    'password': 'AVNS_IsjSis7w5uOuzNZlkDC',
    'database': 'defaultdb'
}


class Movimiento(BaseModel):
    id_turno: int
    tipo_movimiento: str
    producto: str = "Venta general"
    cantidad: float = 1.0
    precio_unitario: float


class ActualizacionPrecio(BaseModel):
    nombre_producto: str
    nuevo_precio: float


def conectar_bd():
    return mysql.connector.connect(**db_config)


@app.get("/")
def inicio():
    return {"mensaje": "API del Sistema de Caja funcionando al 100%"}


@app.get("/turno_actual")
def obtener_turno_actual():
    conexion = conectar_bd()
    cursor = conexion.cursor(dictionary=True)
    sql = "SELECT id_turno, estado FROM turnos WHERE estado = 'ABIERTO' LIMIT 1"
    cursor.execute(sql)
    turno = cursor.fetchone()
    cursor.close()
    conexion.close()

    if turno:
        return turno
    return {"estado": "CERRADO"}


@app.post("/abrir_turno")
def abrir_turno():
    conexion = conectar_bd()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("SELECT id_turno FROM turnos WHERE estado = 'ABIERTO' LIMIT 1")
    existente = cursor.fetchone()

    if existente:
        cursor.close()
        conexion.close()
        return {"mensaje": "Ya hay un turno abierto", "id_turno": existente['id_turno']}

    cursor.execute("INSERT INTO turnos (estado) VALUES ('ABIERTO')")
    conexion.commit()
    nuevo_id = cursor.lastrowid

    cursor.close()
    conexion.close()
    return {"mensaje": "Turno abierto con éxito", "id_turno": nuevo_id}


@app.post("/registrar_movimiento")
def registrar(mov: Movimiento):
    conexion = conectar_bd()
    cursor = conexion.cursor()

    nombre_limpio = mov.producto.strip() if mov.producto else "Venta sin nombre"

    if mov.cantidad <= 0:
        mov.cantidad = 1.0

    sql = """
    INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, precio_unitario)
    VALUES (%s, %s, %s, %s, %s)
    """
    valores = (mov.id_turno, mov.tipo_movimiento, nombre_limpio, mov.cantidad, mov.precio_unitario)
    cursor.execute(sql, valores)

    if mov.tipo_movimiento == 'VENTA' and nombre_limpio != "" and nombre_limpio != "Venta sin nombre":
        sql_prod = "INSERT IGNORE INTO productos (nombre_producto, precio_sugerido) VALUES (%s, %s)"
        cursor.execute(sql_prod, (nombre_limpio, mov.precio_unitario))

    conexion.commit()
    cursor.close()
    conexion.close()
    return {"mensaje": "Registro guardado correctamente"}


@app.delete("/borrar_movimiento/{id_movimiento}")
def borrar_movimiento(id_movimiento: int):
    conexion = conectar_bd()
    cursor = conexion.cursor()
    sql = "DELETE FROM movimientos WHERE id_movimiento = %s"
    cursor.execute(sql, (id_movimiento,))
    conexion.commit()
    cursor.close()
    conexion.close()
    return {"mensaje": "Movimiento cancelado"}


@app.put("/actualizar_precio")
def actualizar_precio(datos: ActualizacionPrecio):
    conexion = conectar_bd()
    cursor = conexion.cursor()

    sql = "UPDATE productos SET precio_sugerido = %s WHERE nombre_producto = %s"
    cursor.execute(sql, (datos.nuevo_precio, datos.nombre_producto))
    conexion.commit()

    filas_afectadas = cursor.rowcount
    cursor.close()
    conexion.close()

    if filas_afectadas > 0:
        return {"mensaje": "Precio actualizado correctamente"}
    else:
        return {"mensaje": "No se encontró el producto en el catálogo"}


@app.get("/corte_caja/{id_turno}")
def hacer_corte(id_turno: int):
    conexion = conectar_bd()
    cursor = conexion.cursor(dictionary=True)

    sql_cierre = "UPDATE turnos SET fecha_cierre = NOW(), estado = 'CERRADO' WHERE id_turno = %s"
    cursor.execute(sql_cierre, (id_turno,))
    conexion.commit()

    cursor.execute("SELECT fecha_apertura FROM turnos WHERE id_turno = %s", (id_turno,))
    res_fecha = cursor.fetchone()
    fecha_apertura = res_fecha['fecha_apertura'] if res_fecha else None

    sql_total = """
        SELECT 
            SUM(CASE WHEN tipo_movimiento IN ('VENTA', 'FONDO_CAJA') THEN total_movimiento ELSE 0 END) -
            SUM(CASE WHEN tipo_movimiento = 'RETIRO' THEN total_movimiento ELSE 0 END) AS total_en_caja
        FROM movimientos WHERE id_turno = %s
    """
    cursor.execute(sql_total, (id_turno,))
    res_total = cursor.fetchone()
    total_en_caja = float(res_total['total_en_caja']) if res_total and res_total['total_en_caja'] is not None else 0.0

    sql_especificos = """
        SELECT SUM(total_movimiento) AS total_especial
        FROM movimientos 
        WHERE id_turno = %s 
        AND tipo_movimiento = 'VENTA'
        AND (producto LIKE '%cigarro%' OR producto LIKE '%time%')
    """
    cursor.execute(sql_especificos, (id_turno,))
    res_especial = cursor.fetchone()
    total_especial = float(res_especial['total_especial']) if res_especial and res_especial[
        'total_especial'] is not None else 0.0

    total_neto = total_en_caja - total_especial
    cursor.close()
    conexion.close()

    return {
        "total_en_caja": total_en_caja,
        "total_cigarros_time": total_especial,
        "total_neto": total_neto,
        "fecha_apertura": fecha_apertura
    }


# --- NUEVA RUTA: Consulta la lista de todos los turnos que ya se cerraron ---
@app.get("/historial_turnos")
def historial_turnos():
    conexion = conectar_bd()
    cursor = conexion.cursor(dictionary=True)
    # Trae los últimos 30 cortes, ordenados del más reciente al más antiguo
    sql = "SELECT id_turno, fecha_apertura, fecha_cierre FROM turnos WHERE estado = 'CERRADO' ORDER BY id_turno DESC LIMIT 30"
    cursor.execute(sql)
    turnos = cursor.fetchall()
    cursor.close()
    conexion.close()
    return turnos


@app.get("/resumen_turno/{id_turno}")
def resumen_turno(id_turno: int):
    conexion = conectar_bd()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("SELECT fecha_apertura FROM turnos WHERE id_turno = %s", (id_turno,))
    res_fecha = cursor.fetchone()
    fecha_apertura = res_fecha['fecha_apertura'] if res_fecha else None

    sql_total = """
        SELECT 
            SUM(CASE WHEN tipo_movimiento IN ('VENTA', 'FONDO_CAJA') THEN total_movimiento ELSE 0 END) -
            SUM(CASE WHEN tipo_movimiento = 'RETIRO' THEN total_movimiento ELSE 0 END) AS total_en_caja
        FROM movimientos WHERE id_turno = %s
    """
    cursor.execute(sql_total, (id_turno,))
    res_total = cursor.fetchone()
    total_en_caja = float(res_total['total_en_caja']) if res_total and res_total['total_en_caja'] is not None else 0.0

    sql_especificos = """
        SELECT SUM(total_movimiento) AS total_especial
        FROM movimientos 
        WHERE id_turno = %s 
        AND tipo_movimiento = 'VENTA'
        AND (producto LIKE '%cigarro%' OR producto LIKE '%time%')
    """
    cursor.execute(sql_especificos, (id_turno,))
    res_especial = cursor.fetchone()
    total_especial = float(res_especial['total_especial']) if res_especial and res_especial[
        'total_especial'] is not None else 0.0

    total_neto = total_en_caja - total_especial
    cursor.close()
    conexion.close()

    return {
        "total_en_caja": total_en_caja,
        "total_cigarros_time": total_especial,
        "total_neto": total_neto,
        "fecha_apertura": fecha_apertura
    }


@app.get("/movimientos_turno/{id_turno}")
def obtener_movimientos(id_turno: int):
    conexion = conectar_bd()
    cursor = conexion.cursor(dictionary=True)
    sql = "SELECT id_movimiento, cantidad, producto, total_movimiento, tipo_movimiento FROM movimientos WHERE id_turno = %s ORDER BY id_movimiento DESC"
    cursor.execute(sql, (id_turno,))
    movimientos = cursor.fetchall()
    cursor.close()
    conexion.close()
    return movimientos


@app.get("/buscar_productos")
def buscar_productos(q: str = ""):
    conexion = conectar_bd()
    cursor = conexion.cursor(dictionary=True)
    if q == "":
        sql = """
            SELECT p.nombre_producto, p.precio_sugerido 
            FROM productos p
            LEFT JOIN (SELECT producto, COUNT(*) as ventas FROM movimientos GROUP BY producto) m 
            ON p.nombre_producto = m.producto
            ORDER BY m.ventas DESC LIMIT 15
        """
        cursor.execute(sql)
    else:
        sql = "SELECT nombre_producto, precio_sugerido FROM productos WHERE nombre_producto LIKE %s LIMIT 10"
        cursor.execute(sql, (f"%{q}%",))

    resultados = cursor.fetchall()
    cursor.close()
    conexion.close()
    return resultados
