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


@router.get("/resumen_dashboard_turno/{id_turno}")
def resumen_dashboard_turno(id_turno: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)

        cursor.execute(
            "SELECT fecha_apertura FROM turnos WHERE id_turno = %s AND id_tienda = %s",
            (id_turno, user.id_tienda)
        )
        turno = cursor.fetchone()
        fecha_apertura = turno['fecha_apertura'] if turno else None

        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN tipo_movimiento IN ('VENTA', 'COBRO_FIADO') THEN total_movimiento ELSE 0 END), 0) AS venta_total,
                COALESCE(SUM(CASE WHEN tipo_movimiento = 'VENTA' THEN cantidad ELSE 0 END), 0) AS productos_vendidos,
                COALESCE(SUM(CASE WHEN tipo_movimiento = 'RETIRO' THEN total_movimiento ELSE 0 END), 0) AS retiros_dia
            FROM movimientos
            WHERE id_turno = %s AND id_tienda = %s
        """, (id_turno, user.id_tienda))
        totales = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(DISTINCT COALESCE(id_lote, CONCAT('m-', id_movimiento))) AS n_tickets
            FROM movimientos
            WHERE id_turno = %s AND id_tienda = %s AND tipo_movimiento = 'VENTA'
        """, (id_turno, user.id_tienda))
        n_tickets = cursor.fetchone()['n_tickets'] or 0

        cursor.execute("""
            SELECT producto, total_movimiento AS monto, TIME_FORMAT(fecha_hora, '%H:%i') AS hora
            FROM movimientos
            WHERE id_turno = %s AND id_tienda = %s AND tipo_movimiento = 'COBRO_FIADO'
            ORDER BY id_movimiento DESC
        """, (id_turno, user.id_tienda))
        abonos = []
        for a in cursor.fetchall():
            partes = (a['producto'] or '').split(' — ', 1)
            cliente = partes[1] if len(partes) == 2 else (a['producto'] or 'Cliente')
            abonos.append({"cliente": cliente, "monto": float(a['monto']), "hora": a['hora']})

        # ── Fiados nuevos del turno ──────────────────────────────────────────
        # OJO: detalle_fiado no guarda id_turno (limitación del esquema actual),
        # se aproxima con fecha_hora >= apertura del turno. Si hubiera más de un
        # turno el mismo día en la misma tienda, podría arrastrar fiados de un
        # turno anterior ya cerrado. Caso raro hoy, queda documentado.
        fiados = []
        if fecha_apertura:
            cursor.execute("""
                SELECT c.nombre AS cliente, SUM(df.cantidad) AS cantidad_total,
                       MAX(df.fecha_hora) AS ultima_hora
                FROM detalle_fiado df
                JOIN cuentas_fiado cf ON cf.id_cuenta = df.id_cuenta
                JOIN clientes c ON c.id_cliente = cf.id_cliente
                WHERE df.id_tienda = %s AND df.fecha_hora >= %s
                GROUP BY df.id_cuenta, c.nombre
                ORDER BY ultima_hora DESC
            """, (user.id_tienda, fecha_apertura))
            for f in cursor.fetchall():
                fiados.append({
                    "cliente": f['cliente'],
                    "cantidad": float(f['cantidad_total']),
                    "hora": f['ultima_hora'].strftime('%H:%M') if f['ultima_hora'] else None
                })

        cursor.execute("""
            SELECT HOUR(fecha_hora) AS hora, SUM(total_movimiento) AS total
            FROM movimientos
            WHERE id_turno = %s AND id_tienda = %s AND tipo_movimiento IN ('VENTA', 'COBRO_FIADO')
            GROUP BY HOUR(fecha_hora)
            ORDER BY hora
        """, (id_turno, user.id_tienda))
        grafica = [{"hora": g['hora'], "total": float(g['total'])} for g in cursor.fetchall()]

        return {
            "venta_total": float(totales['venta_total']),
            "productos_vendidos": float(totales['productos_vendidos']),
            "num_ventas": n_tickets + len(abonos),
            "retiros_dia": float(totales['retiros_dia']),
            "abonos": abonos,
            "fiados": fiados,
            "grafica": grafica,
        }
    finally:
        if cursor:
            cursor.close()
        conexion.close()