from fastapi import APIRouter, Depends, HTTPException
from database import conectar_bd
from auth import get_current_user
from models import TokenData, Movimiento, ActualizacionPrecio, VentaLote
from helpers import _log

router = APIRouter()


@router.post("/registrar_movimiento")
def registrar(mov: Movimiento, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        nombre_limpio = mov.producto.strip() if mov.producto else "Venta sin nombre"
        if mov.cantidad <= 0:
            mov.cantidad = 1.0

        conexion.start_transaction()
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
                "INSERT IGNORE INTO productos (nombre_producto, precio_sugerido, activo, id_tienda) VALUES (%s, %s, 1, %s)",
                (nombre_limpio, mov.precio_unitario, user.id_tienda)
            )
            # ← CORRECCIÓN: bloquear la fila ANTES de modificarla
            cursor.execute("""
                SELECT id_producto FROM productos
                WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
                FOR UPDATE
            """, (nombre_limpio, user.id_tienda))
            if cursor.fetchone():  # solo descontar si el producto existe en catálogo
                cursor.execute("""
                    UPDATE productos
                    SET stock_actual = stock_actual - %s
                    WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
                """, (float(mov.cantidad), nombre_limpio, user.id_tienda))

        conexion.commit()
        return {"mensaje": "Registro guardado correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar movimiento: {str(e)}")
    finally:
        if cursor is not None:
            cursor.close()
        conexion.close()


@router.delete("/borrar_movimiento/{id_movimiento}")
def borrar_movimiento(id_movimiento: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        conexion.start_transaction()
        cursor.execute(
            "SELECT tipo_movimiento, producto, cantidad, cantidad_real FROM movimientos WHERE id_movimiento = %s AND id_tienda = %s",
            (id_movimiento, user.id_tienda)
        )
        mov = cursor.fetchone()
        if not mov:
            return {"mensaje": "Movimiento no encontrado"}

        cursor.execute("DELETE FROM movimientos WHERE id_movimiento = %s AND id_tienda = %s",
                       (id_movimiento, user.id_tienda))

        if mov["tipo_movimiento"] == "VENTA" and mov["producto"]:
            cantidad_devolver = float(mov["cantidad_real"] if mov["cantidad_real"] is not None else mov["cantidad"])
            cursor.execute("""
                    UPDATE productos
                    SET stock_actual = stock_actual + %s
                    WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
                """, (cantidad_devolver, mov["producto"], user.id_tienda))

        _log(cursor, user.id_tienda, user.id_usuario, "BORRAR_MOVIMIENTO",
             f"id={id_movimiento} tipo={mov['tipo_movimiento']} producto={mov['producto']} cantidad={mov['cantidad']}")

        conexion.commit()
        return {"mensaje": "Movimiento cancelado"}
    except Exception as e:
        if conexion:
            conexion.rollback()
        raise HTTPException(status_code=500, detail=f"Error al cancelar movimiento: {str(e)}")
    finally:
        if cursor is not None:
            cursor.close()
        conexion.close()


@router.put("/actualizar_precio")
def actualizar_precio(datos: ActualizacionPrecio, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
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
        if cursor is not None:  # ← proteger el close
            cursor.close()
        conexion.close()


@router.post("/registrar_venta_lote")
def registrar_venta_lote(venta: VentaLote, user: TokenData = Depends(get_current_user)):
    if not venta.items:
        return {"error": "Sin items"}
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()

        conexion.start_transaction()

        # Validación del turno (ya la tienes ✅)
        cursor.execute(
            "SELECT id_turno FROM turnos WHERE id_turno = %s AND id_tienda = %s AND estado = 'ABIERTO'",
            (venta.id_turno, user.id_tienda)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Turno no válido para esta tienda")

        for i in venta.items:
            nombre_limpio = i.producto.strip() if i.producto else "Venta sin nombre"

            # ── NUEVA VALIDACIÓN: solo actualizar stock si el producto existe y pertenece a esta tienda
            cursor.execute("""
                INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, cantidad_real, precio_unitario, id_tienda)
                VALUES (%s, 'VENTA', %s, %s, %s, %s, %s)
            """, (venta.id_turno, nombre_limpio, i.cantidad, i.cantidad_real, i.precio_unitario, user.id_tienda))

            # Descontar stock: por id_producto si viene, si no por nombre
            if i.id_producto:
                cursor.execute("""
                    SELECT id_producto FROM productos
                    WHERE id_producto = %s AND activo = 1 AND id_tienda = %s
                    FOR UPDATE
                """, (i.id_producto, user.id_tienda))
                if cursor.fetchone():
                    cursor.execute("""
                        UPDATE productos
                        SET stock_actual = stock_actual - %s
                        WHERE id_producto = %s AND id_tienda = %s
                    """, (float(i.cantidad_real if i.cantidad_real is not None else i.cantidad), i.id_producto, user.id_tienda))
            else:
                cursor.execute("""
                    SELECT id_producto FROM productos
                    WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
                    FOR UPDATE
                """, (nombre_limpio, user.id_tienda))
                if cursor.fetchone():
                    cursor.execute("""
                        UPDATE productos
                        SET stock_actual = stock_actual - %s
                        WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
                    """, (float(i.cantidad_real if i.cantidad_real is not None else i.cantidad), nombre_limpio, user.id_tienda))

            # Solo crear producto nuevo si NO viene id_producto (producto sin código escrito a mano)
            if not i.id_producto:
                cursor.execute("""
                    INSERT IGNORE INTO productos (nombre_producto, precio_sugerido, activo, id_tienda)
                    SELECT %s, %s, 1, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM productos
                        WHERE nombre_producto = %s AND id_tienda = %s AND activo = 1
                    )
                """, (nombre_limpio, i.precio_unitario, user.id_tienda,
                      nombre_limpio, user.id_tienda))

        conexion.commit()
        return {"ok": True, "registrados": len(venta.items)}
    except HTTPException:
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar venta: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        conexion.close()