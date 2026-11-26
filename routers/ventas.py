import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from database import conectar_bd
from auth import get_current_user
from models import TokenData, Movimiento, ActualizacionPrecio, VentaLote
from helpers import _log, _idem_reservar, _idem_guardar, _idem_huella

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/registrar_movimiento")
def registrar(mov: Movimiento, user: TokenData = Depends(get_current_user),
              idempotency_key: str | None = Header(default=None, max_length=64)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        nombre_limpio = mov.producto.strip() if mov.producto else "Venta sin nombre"
        if mov.cantidad <= 0:
            mov.cantidad = 1.0

        conexion.start_transaction()

        # #66: si este mismo envío ya se procesó (reintento), devolver la respuesta original
        huella = _idem_huella(mov.model_dump(mode="json"))
        previa = _idem_reservar(cursor, user.id_tienda, idempotency_key, "movimiento", huella)
        if previa is not None:
            conexion.rollback()
            return previa

        # ── VALIDACIÓN ANTI-FUGA MULTI-TENANT ─────────────────────
        # #104: el fondo usa FOR UPDATE para que dos dispositivos no lo registren a la vez
        candado = "FOR UPDATE" if mov.tipo_movimiento == 'FONDO_CAJA' else "FOR SHARE"
        cursor.execute(
            "SELECT id_turno FROM turnos WHERE id_turno = %s AND id_tienda = %s AND estado = 'ABIERTO' " + candado,
            (mov.id_turno, user.id_tienda)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Turno no válido para esta tienda")
        # ──────────────────────────────────────────────────────────

        # #104: un solo fondo de caja por turno
        if mov.tipo_movimiento == 'FONDO_CAJA':
            cursor.execute(
                "SELECT id_movimiento FROM movimientos WHERE id_turno = %s AND id_tienda = %s AND tipo_movimiento = 'FONDO_CAJA' LIMIT 1",
                (mov.id_turno, user.id_tienda)
            )
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="Este turno ya tiene fondo de caja. Para corregirlo, cancélalo en Movimientos y regístralo de nuevo.")

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

        respuesta = {"mensaje": "Registro guardado correctamente"}
        _idem_guardar(cursor, user.id_tienda, idempotency_key, respuesta, huella)
        conexion.commit()
        return respuesta
    except HTTPException:
        conexion.rollback()
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        logger.exception("Error al registrar movimiento")
        raise HTTPException(status_code=500, detail="Error al registrar movimiento")
    finally:
        if cursor is not None:
            cursor.close()
        conexion.close()


def _revertir_abono_de_lote(cursor, id_tienda: int, id_lote: str):
    """#64: al cancelar un COBRO_FIADO, deshace el abono ligado (mismo id_lote).
    - Cuenta aún ABIERTA: solo se borra el abono.
    - Cuenta SALDADA y el cliente sin otra cuenta abierta: se borra el abono y se reabre la cuenta.
    - Cuenta SALDADA y el cliente ya tiene otra abierta: se borra el abono y el monto se suma
      a la deuda de la cuenta abierta como una línea «Abono cancelado dd/mm».
    Los abonos anteriores a #64 no tienen id_lote: no se encuentran y todo queda como antes.
    Llamar dentro de la transacción del borrado, con cursor(dictionary=True)."""
    cursor.execute("""
        SELECT a.id_abono, a.id_cuenta, a.monto, a.fecha_hora, cf.id_cliente, cf.estado
        FROM abonos a
        JOIN cuentas_fiado cf ON cf.id_cuenta = a.id_cuenta AND cf.id_tienda = a.id_tienda
        WHERE a.id_lote = %s AND a.id_tienda = %s
        LIMIT 1
        FOR UPDATE
    """, (id_lote, id_tienda))
    abono = cursor.fetchone()
    if not abono:
        return
    cursor.execute("DELETE FROM abonos WHERE id_abono = %s AND id_tienda = %s",
                   (abono["id_abono"], id_tienda))
    if abono["estado"] != "SALDADA":
        return
    cursor.execute("""
        SELECT id_cuenta FROM cuentas_fiado
        WHERE id_cliente = %s AND estado = 'ABIERTA' AND id_tienda = %s
        LIMIT 1
        FOR UPDATE
    """, (abono["id_cliente"], id_tienda))
    abierta = cursor.fetchone()
    if not abierta:
        cursor.execute("UPDATE cuentas_fiado SET estado = 'ABIERTA' WHERE id_cuenta = %s AND id_tienda = %s",
                       (abono["id_cuenta"], id_tienda))
        return
    cursor.execute("""
        INSERT INTO detalle_fiado (id_cuenta, producto, cantidad, precio, id_tienda)
        VALUES (%s, %s, 1, %s, %s)
    """, (abierta["id_cuenta"], f"Abono cancelado {abono['fecha_hora'].strftime('%d/%m')}",
          abono["monto"], id_tienda))


@router.delete("/borrar_movimiento/{id_movimiento}")
def borrar_movimiento(id_movimiento: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        conexion.start_transaction()
        cursor.execute(
            "SELECT id_turno, tipo_movimiento, producto, cantidad, cantidad_real, id_producto_ref, id_lote FROM movimientos WHERE id_movimiento = %s AND id_tienda = %s FOR UPDATE",
            (id_movimiento, user.id_tienda)
        )
        mov = cursor.fetchone()
        if not mov:
            return {"mensaje": "Movimiento no encontrado"}

        # #64: un turno ya cerrado no se modifica (el corte quedaría distinto al que se entregó)
        cursor.execute(
            "SELECT id_turno FROM turnos WHERE id_turno = %s AND id_tienda = %s AND estado = 'ABIERTO' FOR SHARE",
            (mov["id_turno"], user.id_tienda)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=409, detail="No se puede cancelar: el turno ya está cerrado")

        cursor.execute("DELETE FROM movimientos WHERE id_movimiento = %s AND id_tienda = %s",
                       (id_movimiento, user.id_tienda))

        # #64: cancelar un abono de fiado también deshace el abono (y reabre la cuenta si hace falta)
        if mov["tipo_movimiento"] == "COBRO_FIADO" and mov["id_lote"]:
            _revertir_abono_de_lote(cursor, user.id_tienda, mov["id_lote"])

        if mov["tipo_movimiento"] == "VENTA" and mov["producto"]:
            cantidad_devolver = float(mov["cantidad_real"] if mov["cantidad_real"] is not None else mov["cantidad"])
            if mov["id_producto_ref"]:
                cursor.execute("""
                    UPDATE productos
                    SET stock_actual = stock_actual + %s
                    WHERE id_producto = %s AND id_tienda = %s
                """, (cantidad_devolver, mov["id_producto_ref"], user.id_tienda))
            else:
                cursor.execute("""
                    SELECT id_producto FROM productos
                    WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
                    ORDER BY id_producto
                    LIMIT 1
                """, (mov["producto"], user.id_tienda))
                prod_nombre = cursor.fetchone()
                if prod_nombre:
                    cursor.execute("""
                        UPDATE productos
                        SET stock_actual = stock_actual + %s
                        WHERE id_producto = %s AND id_tienda = %s
                    """, (cantidad_devolver, prod_nombre["id_producto"], user.id_tienda))

        _log(cursor, user.id_tienda, user.id_usuario, "BORRAR_MOVIMIENTO",
             f"id={id_movimiento} tipo={mov['tipo_movimiento']} producto={mov['producto']} cantidad={mov['cantidad']}")

        conexion.commit()
        return {"mensaje": "Movimiento cancelado"}
    except HTTPException:
        conexion.rollback()
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        logger.exception("Error al cancelar movimiento")
        raise HTTPException(status_code=500, detail="Error al cancelar movimiento")
    finally:
        if cursor is not None:
            cursor.close()
        conexion.close()


@router.delete("/borrar_lote/{id_lote}")
def borrar_lote(id_lote: str, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        conexion.start_transaction()
        cursor.execute(
            "SELECT id_turno, tipo_movimiento, producto, cantidad, cantidad_real, id_producto_ref FROM movimientos WHERE id_lote = %s AND id_tienda = %s FOR UPDATE",
            (id_lote, user.id_tienda)
        )
        filas = cursor.fetchall()
        if not filas:
            return {"mensaje": "Ticket no encontrado"}

        # #64: un turno ya cerrado no se modifica
        cursor.execute(
            "SELECT id_turno FROM turnos WHERE id_turno = %s AND id_tienda = %s AND estado = 'ABIERTO' FOR SHARE",
            (filas[0]["id_turno"], user.id_tienda)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=409, detail="No se puede cancelar: el turno ya está cerrado")

        cursor.execute("DELETE FROM movimientos WHERE id_lote = %s AND id_tienda = %s",
                       (id_lote, user.id_tienda))

        # #64: cancelar un abono de fiado también deshace el abono (y reabre la cuenta si hace falta)
        if any(f["tipo_movimiento"] == "COBRO_FIADO" for f in filas):
            _revertir_abono_de_lote(cursor, user.id_tienda, id_lote)

        for mov in filas:
            if mov["tipo_movimiento"] == "VENTA" and mov["producto"]:
                cantidad_devolver = float(mov["cantidad_real"] if mov["cantidad_real"] is not None else mov["cantidad"])
                if mov["id_producto_ref"]:
                    cursor.execute("""
                        UPDATE productos
                        SET stock_actual = stock_actual + %s
                        WHERE id_producto = %s AND id_tienda = %s
                    """, (cantidad_devolver, mov["id_producto_ref"], user.id_tienda))
                else:
                    cursor.execute("""
                        SELECT id_producto FROM productos
                        WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
                        ORDER BY id_producto
                        LIMIT 1
                    """, (mov["producto"], user.id_tienda))
                    prod_nombre = cursor.fetchone()
                    if prod_nombre:
                        cursor.execute("""
                            UPDATE productos
                            SET stock_actual = stock_actual + %s
                            WHERE id_producto = %s AND id_tienda = %s
                        """, (cantidad_devolver, prod_nombre["id_producto"], user.id_tienda))

        _log(cursor, user.id_tienda, user.id_usuario, "BORRAR_LOTE",
             f"id_lote={id_lote} productos={len(filas)}")

        conexion.commit()
        return {"mensaje": "Ticket cancelado", "productos_afectados": len(filas)}
    except HTTPException:
        conexion.rollback()
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        logger.exception("Error al cancelar el ticket")
        raise HTTPException(status_code=500, detail="Error al cancelar el ticket")
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
def registrar_venta_lote(venta: VentaLote, user: TokenData = Depends(get_current_user),
                         idempotency_key: str | None = Header(default=None, max_length=64)):
    if not venta.items:
        return {"error": "Sin items"}
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()

        conexion.start_transaction()

        # #66: si este mismo envío ya se procesó (reintento), devolver la respuesta original
        huella = _idem_huella(venta.model_dump())
        previa = _idem_reservar(cursor, user.id_tienda, idempotency_key, "venta_lote", huella)
        if previa is not None:
            conexion.rollback()
            return previa

        # Validación del turno (ya la tienes ✅)
        cursor.execute(
            "SELECT id_turno FROM turnos WHERE id_turno = %s AND id_tienda = %s AND estado = 'ABIERTO' FOR SHARE",
            (venta.id_turno, user.id_tienda)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Turno no válido para esta tienda")

        ids_prod = list({i.id_producto for i in venta.items if i.id_producto})
        if ids_prod:
            cursor.execute(
                f"SELECT COUNT(*) FROM productos WHERE id_tienda = %s AND id_producto IN ({','.join(['%s'] * len(ids_prod))})",
                [user.id_tienda] + ids_prod
            )
            if cursor.fetchone()[0] != len(ids_prod):
                raise HTTPException(status_code=400, detail="Uno o más productos no pertenecen a esta tienda")

        id_lote = uuid.uuid4().hex[:12]

        for i in venta.items:
            nombre_limpio = i.producto.strip() if i.producto else "Venta sin nombre"

            # ── NUEVA VALIDACIÓN: solo actualizar stock si el producto existe y pertenece a esta tienda
            cursor.execute("""
                INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, cantidad_real, precio_unitario, id_tienda, id_producto_ref, metodo_pago, id_lote)
                VALUES (%s, 'VENTA', %s, %s, %s, %s, %s, %s, %s, %s)
            """, (venta.id_turno, nombre_limpio, i.cantidad, i.cantidad_real, i.precio_unitario, user.id_tienda, i.id_producto or None, venta.metodo_pago, id_lote))

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
                    ORDER BY id_producto
                    LIMIT 1
                    FOR UPDATE
                """, (nombre_limpio, user.id_tienda))
                prod_nombre = cursor.fetchone()
                if prod_nombre:
                    cursor.execute("""
                        UPDATE productos
                        SET stock_actual = stock_actual - %s
                        WHERE id_producto = %s AND id_tienda = %s
                    """, (float(i.cantidad_real if i.cantidad_real is not None else i.cantidad), prod_nombre[0], user.id_tienda))

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

        respuesta = {"ok": True, "registrados": len(venta.items), "id_lote": id_lote}
        _idem_guardar(cursor, user.id_tienda, idempotency_key, respuesta, huella)
        conexion.commit()
        return respuesta
    except HTTPException:
        conexion.rollback()
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        logger.exception("Error al registrar venta")
        raise HTTPException(status_code=500, detail="Error al registrar venta")
    finally:
        if cursor:
            cursor.close()
        conexion.close()