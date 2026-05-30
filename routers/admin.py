from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
import mysql.connector
from database import conectar_bd
from auth import get_current_user, pwd_context
from models import TokenData, TiendaNueva, UsuarioNuevo, ResetPassword, ActualizacionNombreTienda, ActualizacionUsuario, SuscripcionTienda
from helpers import _require_superadmin, _invalidar_cache_tienda

router = APIRouter()


# ── Tiendas ───────────────────────────────────────────────────────────────────

@router.get("/admin/tiendas")
def admin_listar_tiendas(user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.id_tienda, t.nombre_comercial, t.activa,
                   COUNT(DISTINCT u.id_usuario) AS total_usuarios,
                   (SELECT COUNT(*) FROM turnos tr WHERE tr.id_tienda = t.id_tienda
                    AND DATE(tr.fecha_apertura) = CURDATE()) AS turnos_hoy
            FROM tiendas t
            LEFT JOIN usuarios u ON u.id_tienda = t.id_tienda
            GROUP BY t.id_tienda
            ORDER BY t.id_tienda
        """)
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/admin/tiendas")
def admin_crear_tienda(t: TiendaNueva, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    nombre = t.nombre_comercial.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO tiendas (nombre_comercial, activa) VALUES (%s, 1)", (nombre,)
        )
        conexion.commit()
        return {"mensaje": "Tienda creada", "id_tienda": cursor.lastrowid}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.put("/admin/tiendas/{id_tienda}/activar")
def admin_activar_tienda(id_tienda: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute("UPDATE tiendas SET activa = 1 WHERE id_tienda = %s", (id_tienda,))
        conexion.commit()
        return {"mensaje": "Tienda activada"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.put("/admin/tiendas/{id_tienda}/desactivar")
def admin_desactivar_tienda(id_tienda: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute("UPDATE tiendas SET activa = 0 WHERE id_tienda = %s", (id_tienda,))
        # Cierre forzado de cualquier turno abierto en la tienda
        cursor.execute("""
            UPDATE turnos 
            SET estado = 'CERRADO', 
                fecha_cierre = CURRENT_TIMESTAMP 
            WHERE id_tienda = %s AND estado = 'ABIERTO'
        """, (id_tienda,))
        conexion.commit()
        _invalidar_cache_tienda(id_tienda)
        return {"mensaje": "Tienda desactivada"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.put("/admin/tiendas/{id_tienda}/editar")
def admin_editar_tienda(id_tienda: int, datos: ActualizacionNombreTienda, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    nombre = datos.nombre_comercial.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE tiendas SET nombre_comercial = %s WHERE id_tienda = %s",
            (nombre, id_tienda)
        )
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Tienda no encontrada")
        return {"mensaje": "Nombre de tienda actualizado correctamente"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


# ── Usuarios ──────────────────────────────────────────────────────────────────

@router.get("/admin/usuarios")
def admin_listar_usuarios(user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
                    SELECT u.id_usuario, u.username, u.rol, u.id_tienda, t.nombre_comercial
                    FROM usuarios u
                    JOIN tiendas t ON t.id_tienda = u.id_tienda
                    WHERE u.activo = 1
                    ORDER BY u.id_tienda, u.id_usuario
                """)
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/admin/usuarios")
def admin_crear_usuario(u: UsuarioNuevo, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    username = u.username.strip()
    if not username or not u.password:
        raise HTTPException(status_code=400, detail="username y password son obligatorios")
    if u.rol not in ("superadmin", "cajero"):
        raise HTTPException(status_code=400, detail="rol inválido")
    hashed = pwd_context.hash(u.password)
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO usuarios (id_tienda, username, password_hash, rol) VALUES (%s, %s, %s, %s)",
            (u.id_tienda, username, hashed, u.rol)
        )
        conexion.commit()
        return {"mensaje": "Usuario creado", "id_usuario": cursor.lastrowid}
    except mysql.connector.IntegrityError:
        raise HTTPException(status_code=409, detail="El username ya existe")
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.put("/admin/usuarios/{id_usuario}/reset_password")
def admin_reset_password(id_usuario: int, datos: ResetPassword, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    if not datos.nuevo_password:
        raise HTTPException(status_code=400, detail="La contraseña no puede estar vacía")
    hashed = pwd_context.hash(datos.nuevo_password)
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s", (hashed, id_usuario)
        )
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return {"mensaje": "Contraseña actualizada"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.delete("/admin/usuarios/{id_usuario}")
def admin_eliminar_usuario(id_usuario: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    if id_usuario == user.id_usuario:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        # CAMBIO QUIRÚRGICO: Soft-delete en lugar de borrado físico
        cursor.execute("UPDATE usuarios SET activo = 0 WHERE id_usuario = %s", (id_usuario,))
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return {"mensaje": "Usuario eliminado correctamente"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.put("/admin/usuarios/{id_usuario}/editar")
def admin_editar_usuario(id_usuario: int, datos: ActualizacionUsuario, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    if datos.rol not in ("superadmin", "cajero"):
        raise HTTPException(status_code=400, detail="rol inválido")
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        # Verificar que la tienda destino existe
        cursor.execute("SELECT id_tienda FROM tiendas WHERE id_tienda = %s", (datos.id_tienda,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="La tienda destino no existe")
        cursor.execute(
            "UPDATE usuarios SET id_tienda = %s, rol = %s WHERE id_usuario = %s AND activo = 1",
            (datos.id_tienda, datos.rol, id_usuario)
        )
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return {"mensaje": "Usuario actualizado correctamente"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


# ── Ventas del día por tienda ──────────────────────────────────────────────────

@router.get("/admin/ventas_hoy")
def admin_ventas_hoy(user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                t.id_tienda, 
                t.nombre_comercial, 
                t.activa,
                COALESCE(SUM(CASE WHEN m.tipo_movimiento IN ('VENTA','FONDO_CAJA','COBRO_FIADO') 
                                  THEN m.total_movimiento ELSE 0 END), 0) AS ventas_hoy,
                COALESCE(SUM(CASE WHEN m.tipo_movimiento = 'RETIRO' 
                                  THEN m.total_movimiento ELSE 0 END), 0) AS retiros_hoy,
                COUNT(DISTINCT tr.id_turno) AS turnos_hoy
            FROM tiendas t

            -- 1. Buscamos los turnos de HOY o que sigan ABIERTOS (espejo del cajero)
            LEFT JOIN turnos tr ON t.id_tienda = tr.id_tienda 
                AND (DATE(tr.fecha_apertura) = CURDATE() OR tr.estado = 'ABIERTO')

            -- 2. Sumamos TODOS los movimientos de esos turnos exactos
            LEFT JOIN movimientos m ON m.id_turno = tr.id_turno

            GROUP BY t.id_tienda
            ORDER BY t.id_tienda
        """)

        rows = cursor.fetchall()
        for r in rows:
            r['neto_hoy'] = float(r['ventas_hoy']) - float(r['retiros_hoy'])
            r['ventas_hoy'] = float(r['ventas_hoy'])
            r['retiros_hoy'] = float(r['retiros_hoy'])

        return rows
    finally:
        if cursor:
            cursor.close()
        conexion.close()


# ── Máquina del Tiempo (Filtro de Fechas) ──────────────────────────────────────

@router.get("/admin/ventas_reporte")
def admin_ventas_reporte(
    fecha_inicio: str,
    fecha_fin: str,
    user: TokenData = Depends(get_current_user)
):
    _require_superadmin(user)
    try:
        datetime.strptime(fecha_inicio, "%Y-%m-%d")
        datetime.strptime(fecha_fin, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use YYYY-MM-DD")

    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                t.id_tienda,
                t.nombre_comercial,
                t.activa,
                COALESCE(SUM(CASE WHEN m.tipo_movimiento IN ('VENTA','FONDO_CAJA','COBRO_FIADO')
                                  THEN m.total_movimiento ELSE 0 END), 0) AS total_ventas,
                COALESCE(SUM(CASE WHEN m.tipo_movimiento = 'RETIRO'
                                  THEN m.total_movimiento ELSE 0 END), 0) AS total_retiros,
                COUNT(DISTINCT tr.id_turno) AS total_turnos
            FROM tiendas t
            LEFT JOIN turnos tr ON t.id_tienda = tr.id_tienda
                AND DATE(tr.fecha_apertura) BETWEEN %s AND %s
            LEFT JOIN movimientos m ON m.id_turno = tr.id_turno
            GROUP BY t.id_tienda
            ORDER BY t.id_tienda
        """, (fecha_inicio, fecha_fin))

        rows = cursor.fetchall()
        for r in rows:
            r['total_ventas'] = float(r['total_ventas'])
            r['total_retiros'] = float(r['total_retiros'])
            r['total_neto'] = r['total_ventas'] - r['total_retiros']

        return {
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "tiendas": rows
        }
    finally:
        if cursor:
            cursor.close()
        conexion.close()


# ── Control de Suscripciones ──────────────────────────────────────────────────

@router.get("/admin/tiendas/{id_tienda}/suscripcion")
def admin_obtener_suscripcion(id_tienda: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_tienda, nombre_comercial, dia_corte, monto_mensual, estado_pago FROM tiendas WHERE id_tienda = %s",
            (id_tienda,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tienda no encontrada")
        row['monto_mensual'] = float(row['monto_mensual'])
        return row
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.put("/admin/tiendas/{id_tienda}/suscripcion")
def admin_actualizar_suscripcion(id_tienda: int, datos: SuscripcionTienda, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    if datos.estado_pago not in ("AL_DIA", "ATRASADO"):
        raise HTTPException(status_code=400, detail="estado_pago inválido. Use AL_DIA o ATRASADO")
    if not (1 <= datos.dia_corte <= 31):
        raise HTTPException(status_code=400, detail="dia_corte debe ser un número entre 1 y 31")
    if datos.monto_mensual < 0:
        raise HTTPException(status_code=400, detail="monto_mensual no puede ser negativo")
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE tiendas SET dia_corte = %s, monto_mensual = %s, estado_pago = %s WHERE id_tienda = %s",
            (datos.dia_corte, datos.monto_mensual, datos.estado_pago, id_tienda)
        )
        conexion.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Tienda no encontrada")
        return {"mensaje": "Suscripción actualizada correctamente"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


# ── Modo "Dios" (Soporte Técnico) ─────────────────────────────────────────────

@router.get("/admin/tienda/{id_tienda}/inventario")
def admin_inventario_tienda(id_tienda: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT nombre_comercial FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        tienda = cursor.fetchone()
        if not tienda:
            raise HTTPException(status_code=404, detail="Tienda no encontrada")
        cursor.execute("""
            SELECT id_producto, codigo_barras, nombre_producto,
                   precio_sugerido, stock_actual, stock_minimo,
                   proveedor, fecha_caducidad, unidad_medida
            FROM productos
            WHERE activo = 1 AND id_tienda = %s
            ORDER BY nombre_producto ASC
        """, (id_tienda,))
        productos = cursor.fetchall()
        return {
            "id_tienda": id_tienda,
            "nombre_comercial": tienda['nombre_comercial'],
            "total_productos": len(productos),
            "productos": productos
        }
    finally:
        if cursor:
            cursor.close()
        conexion.close()


# ─── Log de Auditoría ──────────────────────────────────────────────────────────

@router.get("/admin/log_auditoria/{id_tienda}")
def admin_log_auditoria(id_tienda: int, user: TokenData = Depends(get_current_user)):
    _require_superadmin(user)
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT l.id_log, u.username, l.accion, l.detalle,
                   DATE_FORMAT(l.fecha_hora, '%d/%m/%Y %H:%i') AS fecha_hora
            FROM log_auditoria l
            JOIN usuarios u ON u.id_usuario = l.id_usuario
            WHERE l.id_tienda = %s
            ORDER BY l.fecha_hora DESC LIMIT 100
        """, (id_tienda,))
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        conexion.close()