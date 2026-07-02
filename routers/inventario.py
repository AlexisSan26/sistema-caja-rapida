from fastapi import APIRouter, Depends, HTTPException
from database import conectar_bd
from auth import get_current_user
from models import TokenData, ProductoNuevo, ActualizacionProducto, MermaProducto
from helpers import _log

router = APIRouter()


@router.get("/buscar_productos")
def buscar_productos(q: str = "", user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
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
        if cursor:
            cursor.close()
        conexion.close()


@router.get("/productos")
def obtener_todos_productos(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_producto, nombre_producto, precio_sugerido, codigo_barras, unidad_medida FROM productos WHERE activo = 1 AND id_tienda = %s ORDER BY nombre_producto",
            (user.id_tienda,)
        )
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.get("/producto_por_codigo/{codigo}")
def producto_por_codigo(codigo: str, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
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
        if len(codigo) > 4:
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
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/registrar_producto")
def registrar_producto(p: ProductoNuevo, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO productos
            (codigo_barras, nombre_producto, precio_sugerido, precio_costo,
             stock_actual, stock_minimo, proveedor, fecha_caducidad, activo, id_tienda, unidad_medida)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
        """, (p.codigo_barras or None, p.nombre_producto, p.precio_sugerido, p.precio_costo,
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
        if cursor:
            cursor.close()
        conexion.close()


@router.put("/actualizar_producto/{id_producto}")
def actualizar_producto(id_producto: int, datos: ActualizacionProducto, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute("""
            UPDATE productos SET
                nombre_producto = %s,
                precio_sugerido = %s,
                precio_costo    = %s,
                stock_actual    = %s,
                stock_minimo    = %s,
                proveedor       = %s,
                codigo_barras   = %s,
                fecha_caducidad = %s,
                unidad_medida   = %s
            WHERE id_producto = %s AND activo = 1 AND id_tienda = %s
        """, (
            datos.nombre_producto, datos.precio_sugerido, datos.precio_costo,
            datos.stock_actual, datos.stock_minimo,
            datos.proveedor or None, datos.codigo_barras or None,
            datos.fecha_caducidad or None, datos.unidad_medida, id_producto, user.id_tienda
        ))
        conexion.commit()
        if cursor.rowcount > 0:
            return {"mensaje": "Producto actualizado correctamente"}
        return {"mensaje": "No se encontró el producto"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.delete("/eliminar_producto/{id_producto}")
def eliminar_producto(id_producto: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
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
        if cursor:
            cursor.close()
        conexion.close()


@router.get("/inventario")
def listar_inventario(q: str = "", proveedor: str = "", user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        sql = """SELECT id_producto, codigo_barras, nombre_producto,
                        precio_sugerido, precio_costo, stock_actual, stock_minimo,
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
        if cursor:
            cursor.close()
        conexion.close()


@router.get("/alertas")
def obtener_alertas(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
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
        if cursor:
            cursor.close()
        conexion.close()


@router.get("/proveedores")
def listar_proveedores(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT DISTINCT proveedor FROM productos WHERE proveedor IS NOT NULL AND activo = 1 AND id_tienda = %s ORDER BY proveedor",
            (user.id_tienda,)
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/descontar_stock/{id_producto}")
def descontar_stock(id_producto: int, cantidad: float = 1, user: TokenData = Depends(get_current_user)):
    if cantidad <= 0:
        raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a cero")
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE productos SET stock_actual = stock_actual - %s WHERE id_producto = %s AND id_tienda = %s",
            (float(cantidad), id_producto, user.id_tienda)
        )
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        return {"mensaje": "Stock actualizado"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/registrar_merma")
def registrar_merma(m: MermaProducto, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        conexion.start_transaction()
        # Verificar que el producto existe y pertenece a esta tienda
        cursor.execute(
            "SELECT nombre_producto FROM productos WHERE id_producto = %s AND activo = 1 AND id_tienda = %s FOR UPDATE",
            (m.id_producto, user.id_tienda)
        )
        producto = cursor.fetchone()
        if not producto:
            conexion.rollback()
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        cursor.execute(
            "UPDATE productos SET stock_actual = stock_actual - %s WHERE id_producto = %s AND id_tienda = %s",
            (m.cantidad, m.id_producto, user.id_tienda)
        )
        # Leer el stock RESULTANTE en el mismo contexto transaccional
        cursor.execute(
            "SELECT stock_actual FROM productos WHERE id_producto = %s AND id_tienda = %s",
            (m.id_producto, user.id_tienda)
        )
        stock_resultante = float(cursor.fetchone()['stock_actual'])

        cursor.execute("""
            INSERT INTO entradas_mercancia (id_producto, cantidad, notas, id_tienda)
            VALUES (%s, %s, %s, %s)
        """, (m.id_producto, -m.cantidad, f"[MERMA — {m.motivo}]", user.id_tienda))

        _log(cursor, user.id_tienda, user.id_usuario, "MERMA",
             f"producto_id={m.id_producto} cantidad={-m.cantidad} motivo={m.motivo}")

        conexion.commit()
        return {
            "mensaje": f"Merma de {m.cantidad} unidades registrada para {producto['nombre_producto']}",
            "advertencia": "Stock quedó en negativo, recuerda registrar la entrada pendiente" if stock_resultante < 0 else None
        }
    except HTTPException:
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar merma: {str(e)}")
    finally:
        if cursor is not None:
            cursor.close()
        conexion.close()