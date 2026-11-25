import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from database import conectar_bd
from auth import get_current_user
from models import TokenData, EntradaLote
from helpers import _idem_reservar, _idem_guardar, _idem_huella

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/entrada_mercancia_lote")
def entrada_mercancia_lote(lote: EntradaLote, user: TokenData = Depends(get_current_user),
                           idempotency_key: str | None = Header(default=None, max_length=64)):
    if not lote.items:
        return {"error": "El lote está vacío"}
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        conexion.start_transaction()

        # #66: si este mismo lote ya se procesó (reintento), devolver la respuesta original
        huella = _idem_huella(lote.model_dump())
        previa = _idem_reservar(cursor, user.id_tienda, idempotency_key, "entrada_lote", huella)
        if previa is not None:
            conexion.rollback()
            return previa

        ids = list({item.id_producto for item in lote.items})
        cursor.execute(
            f"SELECT COUNT(*) FROM productos WHERE id_tienda = %s AND id_producto IN ({','.join(['%s'] * len(ids))})",
            [user.id_tienda] + ids
        )
        if cursor.fetchone()[0] != len(ids):
            raise HTTPException(status_code=400, detail="Uno o más productos no pertenecen a esta tienda")
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
            if item.precio_costo is not None:
                cursor.execute(
                    "UPDATE productos SET precio_costo = %s WHERE id_producto = %s AND id_tienda = %s",
                    (item.precio_costo, item.id_producto, user.id_tienda)
                )
            cursor.execute("""
                INSERT INTO entradas_mercancia (id_producto, cantidad, fecha_caducidad, notas, precio_costo, id_tienda)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
            item.id_producto, item.cantidad, item.fecha_caducidad or None, lote.nota_general or None, item.precio_costo, user.id_tienda))
        respuesta = {"mensaje": f"Se registraron {len(lote.items)} productos correctamente"}
        _idem_guardar(cursor, user.id_tienda, idempotency_key, respuesta, huella)
        conexion.commit()
        return respuesta
    except HTTPException:
        if conexion:
            conexion.rollback()  # #66: también libera la clave si el lote se rechaza
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        logger.exception("Error al registrar lote")
        raise HTTPException(status_code=500, detail="Error al registrar lote")
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
                   e.notas, e.fecha_caducidad, e.precio_costo
            FROM entradas_mercancia e
            JOIN productos p ON p.id_producto = e.id_producto AND p.id_tienda = e.id_tienda
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