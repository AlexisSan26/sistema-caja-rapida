import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from database import conectar_bd
from auth import get_current_user
from models import TokenData

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/reporte_productos")
def reporte_productos(dias: int = 7, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        fecha_inicio = datetime.now() - timedelta(days=dias)
        cursor.execute("""
            SELECT producto,
                   SUM(unidades) AS unidades_vendidas,
                   SUM(total) AS total_vendido
            FROM (
                SELECT producto, COALESCE(cantidad_real, cantidad) AS unidades,
                       COALESCE(cantidad_real, cantidad) * precio_unitario AS total
                FROM movimientos
                WHERE tipo_movimiento = 'VENTA' AND id_tienda = %s AND fecha_hora >= %s
                UNION ALL
                SELECT producto, cantidad AS unidades,
                       COALESCE(monto_real, cantidad * precio) AS total
                FROM detalle_fiado
                WHERE id_tienda = %s AND fecha_hora >= %s
            ) t
            GROUP BY producto
            ORDER BY unidades_vendidas DESC
            LIMIT 10
        """, (user.id_tienda, fecha_inicio, user.id_tienda, fecha_inicio))
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        conexion.close()