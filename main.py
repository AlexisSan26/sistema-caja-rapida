import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from enum import Enum
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

db_config = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 28257)),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
}


# ─── Modelos ──────────────────────────────────────────────────────────────────
class TiposPermitidos(str, Enum):
    VENTA = "VENTA"
    FIADO = "FIADO"
    RETIRO = "RETIRO"
    FONDO_CAJA = "FONDO_CAJA"
    COBRO_FIADO = "COBRO_FIADO"

class Movimiento(BaseModel):
    id_turno: int
    tipo_movimiento: TiposPermitidos  # <-- ¡Aquí está el nuevo candado!
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

# ─── Modelos fiados (nuevos) ──────────────────────────────────────────────────
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


# ─── Helpers ──────────────────────────────────────────────────────────────────
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
            SUM(CASE WHEN tipo_movimiento IN ('VENTA', 'FONDO_CAJA', 'COBRO_FIADO') THEN total_movimiento ELSE 0 END) -
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

        cursor.execute("""
            INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, precio_unitario)
            VALUES (%s, %s, %s, %s, %s)
        """, (mov.id_turno, mov.tipo_movimiento, nombre_limpio, mov.cantidad, mov.precio_unitario))

        # ── Descuenta stock automáticamente en ventas ─────────────────────────
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
            else:
                # Descuenta stock si el producto existe en catálogo
                cursor.execute("""
                    UPDATE productos
                    SET stock_actual = GREATEST(0, stock_actual - %s)
                    WHERE nombre_producto = %s AND activo = 1
                """, (int(mov.cantidad), nombre_limpio))

        conexion.commit()
        return {"mensaje": "Registro guardado correctamente"}
    finally:
        cursor.close()
        conexion.close()

@app.delete("/borrar_movimiento/{id_movimiento}")
def borrar_movimiento(id_movimiento: int):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        # Obtener datos del movimiento antes de borrar
        cursor.execute(
            "SELECT tipo_movimiento, producto, cantidad FROM movimientos WHERE id_movimiento = %s",
            (id_movimiento,)
        )
        mov = cursor.fetchone()
        if not mov:
            return {"mensaje": "Movimiento no encontrado"}
        cursor.execute("DELETE FROM movimientos WHERE id_movimiento = %s", (id_movimiento,))
        # Revertir stock solo si era una VENTA
        if mov["tipo_movimiento"] == "VENTA" and mov["producto"]:
            cursor.execute("""
                UPDATE productos
                SET stock_actual = stock_actual + %s
                WHERE nombre_producto = %s AND activo = 1
            """, (int(mov["cantidad"]), mov["producto"]))
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

@app.get("/productos")
def obtener_todos_productos():
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT nombre_producto, precio_sugerido, codigo_barras FROM productos WHERE activo = 1 ORDER BY nombre_producto"
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
                   stock_actual, stock_minimo, proveedor, fecha_caducidad, codigo_barras
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

@app.put("/actualizar_producto/{id_producto}")
def actualizar_producto(id_producto: int, datos: ActualizacionProducto):
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
            WHERE id_producto = %s AND activo = 1
        """, (
            datos.nombre_producto, datos.precio_sugerido,
            datos.stock_actual, datos.stock_minimo,
            datos.proveedor or None, datos.codigo_barras or None,
            datos.fecha_caducidad or None, id_producto
        ))
        conexion.commit()
        if cursor.rowcount > 0:
            return {"mensaje": "Producto actualizado correctamente"}
        return {"mensaje": "No se encontró el producto"}
    finally:
        cursor.close()
        conexion.close()

@app.delete("/eliminar_producto/{id_producto}")
def eliminar_producto(id_producto: int):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        # Soft delete: Cambiamos el estado a 2 (Inactivo) en lugar de borrarlo
        cursor.execute(
            "UPDATE productos SET activo = 2 WHERE id_producto = %s",
            (id_producto,)
        )
        conexion.commit()
        if cursor.rowcount > 0:
            return {"mensaje": "Producto eliminado del sistema (archivado)"}
        return {"mensaje": "No se encontró el producto o ya estaba inactivo"}
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


# ─── Endpoints de fiados (nuevos) ─────────────────────────────────────────────

@app.get("/clientes")
def listar_clientes():
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.id_cliente, c.nombre, c.telefono,
                   COALESCE(
                     (SELECT SUM(df.cantidad * df.precio)
                      FROM detalle_fiado df
                      JOIN cuentas_fiado cf ON df.id_cuenta = cf.id_cuenta
                      WHERE cf.id_cliente = c.id_cliente AND cf.estado = 'ABIERTA')
                   , 0) -
                   COALESCE(
                     (SELECT SUM(a.monto)
                      FROM abonos a
                      JOIN cuentas_fiado cf ON a.id_cuenta = cf.id_cuenta
                      WHERE cf.id_cliente = c.id_cliente AND cf.estado = 'ABIERTA')
                   , 0) AS saldo_actual
            FROM clientes c
            WHERE c.activo = 1
            ORDER BY c.nombre ASC
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conexion.close()

@app.post("/clientes")
def crear_cliente(c: ClienteNuevo):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO clientes (nombre, telefono) VALUES (%s, %s)",
            (c.nombre.strip(), c.telefono or None)
        )
        id_cliente = cursor.lastrowid
        # Abre cuenta de fiado automáticamente
        cursor.execute(
            "INSERT INTO cuentas_fiado (id_cliente) VALUES (%s)",
            (id_cliente,)
        )
        conexion.commit()
        return {"mensaje": "Cliente registrado", "id_cliente": id_cliente}
    finally:
        cursor.close()
        conexion.close()

@app.delete("/clientes/{id_cliente}")
def eliminar_cliente(id_cliente: int):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        # Verificar si tiene saldo pendiente
        cursor.execute("""
            SELECT COALESCE(SUM(df.cantidad * df.precio), 0) - COALESCE(SUM(a.monto), 0) AS saldo
            FROM cuentas_fiado cf
            LEFT JOIN detalle_fiado df ON df.id_cuenta = cf.id_cuenta
            LEFT JOIN abonos a ON a.id_cuenta = cf.id_cuenta
            WHERE cf.id_cliente = %s AND cf.estado = 'ABIERTA'
        """, (id_cliente,))
        row = cursor.fetchone()
        if row and float(row["saldo"]) > 0:
            return {"error": f"El cliente tiene saldo pendiente de ${float(row['saldo']):.2f}. Salda la cuenta antes de eliminar."}
        cursor.execute("UPDATE clientes SET activo = 0 WHERE id_cliente = %s", (id_cliente,))
        conexion.commit()
        return {"mensaje": "Cliente eliminado"}
    finally:
        cursor.close()
        conexion.close()

@app.get("/cuenta_fiado/{id_cliente}")
def obtener_cuenta(id_cliente: int):
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)
        # Datos del cliente
        cursor.execute(
            "SELECT id_cliente, nombre, telefono FROM clientes WHERE id_cliente = %s AND activo = 1",
            (id_cliente,)
        )
        cliente = cursor.fetchone()
        if not cliente:
            return {"error": "Cliente no encontrado"}

        # Cuenta abierta
        cursor.execute(
            "SELECT id_cuenta FROM cuentas_fiado WHERE id_cliente = %s AND estado = 'ABIERTA' LIMIT 1",
            (id_cliente,)
        )
        cuenta = cursor.fetchone()
        if not cuenta:
            # Abre una cuenta nueva si no existe
            cursor.execute("INSERT INTO cuentas_fiado (id_cliente) VALUES (%s)", (id_cliente,))
            conexion.commit()
            id_cuenta = cursor.lastrowid
        else:
            id_cuenta = cuenta['id_cuenta']

        # Detalle de lo que debe
        cursor.execute("""
            SELECT producto, cantidad, precio, (cantidad * precio) AS subtotal,
                   DATE_FORMAT(fecha_hora, '%d/%m %H:%i') as fecha
            FROM detalle_fiado WHERE id_cuenta = %s
            ORDER BY fecha_hora ASC
        """, (id_cuenta,))
        detalle = cursor.fetchall()

        # Abonos
        cursor.execute("""
            SELECT monto, nota, DATE_FORMAT(fecha_hora, '%d/%m %H:%i') as fecha
            FROM abonos WHERE id_cuenta = %s
            ORDER BY fecha_hora ASC
        """, (id_cuenta,))
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
def agregar_fiado(item: ItemFiado):
    """Registra un producto fiado — no entra a caja, solo a la cuenta del cliente."""
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        # Guarda en detalle_fiado
        cursor.execute("""
            INSERT INTO detalle_fiado (id_cuenta, producto, cantidad, precio)
            VALUES (%s, %s, %s, %s)
        """, (item.id_cuenta, item.producto.strip(), item.cantidad, item.precio))

        # Descuenta stock si el producto existe en catálogo
        cursor.execute("""
            UPDATE productos SET stock_actual = GREATEST(0, stock_actual - %s)
            WHERE nombre_producto = %s AND activo = 1
        """, (int(item.cantidad), item.producto.strip()))

        conexion.commit()
        return {"mensaje": "Fiado registrado correctamente"}
    finally:
        cursor.close()
        conexion.close()

@app.post("/registrar_abono")
def registrar_abono(abono: AbonoFiado):
    """Registra un abono — entra a caja como COBRO_FIADO y descuenta la deuda."""
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor(dictionary=True)

        # Obtener nombre del cliente para el concepto en movimientos
        cursor.execute("""
            SELECT c.nombre FROM clientes c
            JOIN cuentas_fiado cf ON c.id_cliente = cf.id_cliente
            WHERE cf.id_cuenta = %s
        """, (abono.id_cuenta,))
        res = cursor.fetchone()
        nombre_cliente = res['nombre'] if res else "Cliente"

        # Guarda el abono en la tabla de abonos
        cursor.execute(
            "INSERT INTO abonos (id_cuenta, monto, nota) VALUES (%s, %s, %s)",
            (abono.id_cuenta, abono.monto, abono.nota or None)
        )

        # Registra en movimientos para que entre al corte del día
        cursor.execute("""
            INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, precio_unitario)
            VALUES (%s, 'COBRO_FIADO', %s, 1, %s)
        """, (abono.id_turno, f"Abono fiado — {nombre_cliente}", abono.monto))

        # Verifica si el saldo quedó en cero para saldar la cuenta
        cursor.execute("""
            SELECT
                COALESCE(SUM(df.cantidad * df.precio), 0) AS total_fiado
            FROM detalle_fiado df WHERE df.id_cuenta = %s
        """, (abono.id_cuenta,))
        tf = cursor.fetchone()
        cursor.execute(
            "SELECT COALESCE(SUM(monto), 0) AS total_abonos FROM abonos WHERE id_cuenta = %s",
            (abono.id_cuenta,)
        )
        ta = cursor.fetchone()
        saldo_nuevo = float(tf['total_fiado']) - float(ta['total_abonos'])
        if saldo_nuevo <= 0:
            cursor.execute(
                "UPDATE cuentas_fiado SET estado = 'SALDADA' WHERE id_cuenta = %s",
                (abono.id_cuenta,)
            )

        conexion.commit()
        return {"mensaje": "Abono registrado", "saldo_restante": max(0, saldo_nuevo)}
    finally:
        cursor.close()
        conexion.close()

@app.get("/ping")
def ping():
    return {"status": "ok"}

# ─── Venta en lote (todos los productos del carrito en una sola petición) ──────
class ItemVenta(BaseModel):
    producto: str
    cantidad: float = 1.0
    precio_unitario: float

class VentaLote(BaseModel):
    id_turno: int
    items: list[ItemVenta]

@app.post("/registrar_venta_lote")
def registrar_venta_lote(venta: VentaLote):
    if not venta.items:
        return {"error": "Sin items"}
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        for i in venta.items:
            nombre_limpio = i.producto.strip() if i.producto else "Venta sin nombre"
            cursor.execute(
                "INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, precio_unitario) VALUES (%s, 'VENTA', %s, %s, %s)",
                (venta.id_turno, nombre_limpio, i.cantidad, i.precio_unitario)
            )
            # Descuenta stock o crea producto nuevo igual que registrar_movimiento
            cursor.execute("SELECT COUNT(*) FROM productos WHERE nombre_producto = %s", (nombre_limpio,))
            existe = cursor.fetchone()[0] > 0
            if not existe:
                cursor.execute(
                    "INSERT INTO productos (nombre_producto, precio_sugerido, activo) VALUES (%s, %s, 1)",
                    (nombre_limpio, i.precio_unitario)
                )
            else:
                cursor.execute("""
                    UPDATE productos
                    SET stock_actual = GREATEST(0, stock_actual - %s)
                    WHERE nombre_producto = %s AND activo = 1
                """, (int(i.cantidad), nombre_limpio))
        conexion.commit()
        return {"ok": True, "registrados": len(venta.items)}
    finally:
        cursor.close()
        conexion.close()