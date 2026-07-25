import json
import threading
from cachetools import TTLCache
from database import db_pool, conectar_bd


# ─── SEGURIDAD: Cache de autenticación ───────────────────────────────────────
_auth_cache = TTLCache(maxsize=500, ttl=300)
_cache_lock = threading.Lock()


# ─── NUEVO HELPER: Log de Auditoría (Prioridad 4A) ────────────────────────────
def _log(cursor, id_tienda: int, id_usuario: int, accion: str, detalle: str):
    cursor.execute(
        "INSERT INTO log_auditoria (id_tienda, id_usuario, accion, detalle) VALUES (%s, %s, %s, %s)",
        (id_tienda, id_usuario, accion, detalle)
    )


def _calcular_resumen(
    cursor, id_turno: int, id_tienda: int,
    efectivo_declarado: float | None = None,
    reglas_resumen_snapshot: dict | None = None
) -> dict:
    cursor.execute(
        "SELECT fecha_apertura, fecha_cierre, efectivo_declarado, reglas_resumen_cerrado FROM turnos WHERE id_turno = %s AND id_tienda = %s",
        (id_turno, id_tienda)
    )
    res = cursor.fetchone()
    fecha_apertura = res['fecha_apertura'] if res else None
    fecha_cierre = res['fecha_cierre'] if res else None
    # Si no lo pasaron explícito (cierre en curso), usar lo ya guardado en BD (historial)
    if efectivo_declarado is None and res and res.get('efectivo_declarado') is not None:
        efectivo_declarado = float(res['efectivo_declarado'])
    if reglas_resumen_snapshot is None and res and res.get('reglas_resumen_cerrado'):
        try:
            reglas_resumen_snapshot = json.loads(res['reglas_resumen_cerrado'])
        except Exception:
            reglas_resumen_snapshot = None

    cursor.execute("""
        SELECT
            SUM(CASE WHEN tipo_movimiento IN ('VENTA', 'COBRO_FIADO') THEN total_movimiento ELSE 0 END) AS ingresos,
            SUM(CASE WHEN tipo_movimiento = 'RETIRO' THEN total_movimiento ELSE 0 END) AS retiros,
            SUM(CASE WHEN tipo_movimiento = 'FONDO_CAJA' THEN total_movimiento ELSE 0 END) AS fondo
        FROM movimientos WHERE id_turno = %s AND id_tienda = %s
    """, (id_turno, id_tienda))
    res_total = cursor.fetchone()

    total_ingresos = float(res_total['ingresos']) if res_total and res_total['ingresos'] else 0.0
    total_retiros = float(res_total['retiros']) if res_total and res_total['retiros'] else 0.0
    total_fondo = float(res_total['fondo']) if res_total and res_total['fondo'] else 0.0
    # El fondo de caja NO se cuenta en el Subtotal ni en el Neto a entregar:
    # ese dinero se queda en caja para el siguiente turno, solo se muestra informativo.
    total_en_caja = total_ingresos - total_retiros

    if reglas_resumen_snapshot is not None:
        # Turno ya cerrado con desglose congelado: no se toca la Configuración actual,
        # así el historial no se mueve si mañana cambian las reglas.
        resultados_reglas = reglas_resumen_snapshot
        total_deducciones = sum(resultados_reglas.values())
    else:
        # ── Leer reglas configuradas por la tienda (cálculo en vivo) ──
        cursor.execute("SELECT config_resumen FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        conf = cursor.fetchone()
        reglas = []
        gastos_fijos = []
        if conf and conf['config_resumen']:
            try:
                data = json.loads(conf['config_resumen'])
                if isinstance(data, list):
                    reglas = data
                else:
                    reglas = data.get('reglas', [])
                    gastos_fijos = data.get('gastos_fijos', [])
            except Exception:
                pass

        # ── Aplicar reglas dinámicas (claves + ids_productos) ─────
        resultados_reglas = {r['nombre']: 0.0 for r in reglas}
        total_deducciones = 0.0

        for g in gastos_fijos:
            monto_g = float(g.get('monto') or 0)
            if monto_g:
                resultados_reglas[g['nombre']] = resultados_reglas.get(g['nombre'], 0.0) + monto_g
                total_deducciones += monto_g

        if reglas:
            cursor.execute("""
                SELECT m.producto, m.total_movimiento, p.id_producto
                FROM movimientos m
                LEFT JOIN productos p ON p.nombre_producto = m.producto AND p.id_tienda = m.id_tienda
                WHERE m.id_turno = %s AND m.id_tienda = %s AND m.tipo_movimiento = 'VENTA'
            """, (id_turno, id_tienda))
            ventas = cursor.fetchall()
            for v in ventas:
                prod_lower = (v['producto'] or "").lower()
                monto = float(v['total_movimiento'])
                id_prod = v['id_producto']
                for r in reglas:
                    # Coincide por clave O por id_producto seleccionado
                    claves = [k.strip().lower() for k in r.get('claves', '').split(',') if k.strip()]
                    ids_sel = r.get('ids_productos', [])
                    coincide_clave = any(clave in prod_lower for clave in claves)
                    coincide_id = id_prod is not None and id_prod in ids_sel
                    if coincide_clave or coincide_id:
                        resultados_reglas[r['nombre']] += monto
                        total_deducciones += monto
                        break  # evitar doble conteo

    diferencia = None
    if efectivo_declarado is not None:
        total_neto_final = efectivo_declarado - total_deducciones
        diferencia = efectivo_declarado - total_en_caja
    else:
        total_neto_final = total_en_caja - total_deducciones

    return {
        "total_ingresos": total_ingresos,
        "total_fondo": total_fondo,
        "total_retiros": total_retiros,
        "total_en_caja": total_en_caja,
        "reglas_resumen": resultados_reglas,
        "total_neto": total_neto_final,
        "efectivo_real": efectivo_declarado,
        "diferencia": diferencia,
        "fecha_apertura": fecha_apertura,
        "fecha_cierre":   fecha_cierre,
    }


def _invalidar_cache_tienda(id_tienda: int):
    """Borra del cache todos los tokens de usuarios de una tienda."""
    with _cache_lock:
        claves_a_borrar = [k for k in _auth_cache.keys() if k.startswith(f"{id_tienda}:")]
        for k in claves_a_borrar:
            del _auth_cache[k]


def _require_superadmin(user):
    """Helper: lanza 403 si el usuario no es superadmin."""
    from fastapi import HTTPException
    if user.rol != "superadmin":
        raise HTTPException(status_code=403, detail="Acceso restringido al superadmin")