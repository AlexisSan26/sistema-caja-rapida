from fastapi import APIRouter, Depends, HTTPException
from database import conectar_bd
from auth import get_current_user
from models import TokenData, EntradaMercancia, EntradaLote, ResurtidoPorCodigo

router = APIRouter()


@router.post("/entrada_mercancia")
def entrada_mercancia(e: EntradaMercancia, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
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
    except HTTPException:
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar entrada: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/entrada_mercancia_lote")
def entrada_mercancia_lote(lote: EntradaLote, user: TokenData = Depends(get_current_user)):
    if not lote.items:
        return {"error": "El lote está vacío"}
    conexion = conectar_bd()
    cursor = None
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
    except HTTPException:
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar lote: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/resurtir_por_codigo")
def resurtir_por_codigo(r: ResurtidoPorCodigo, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
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
        if cursor:
            cursor.close()
        conexion.close()


@router.get("/historial_entradas")
def historial_entradas(fecha: str = "", user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
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
        if cursor:
            cursor.close()
        conexion.close()