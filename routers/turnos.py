from fastapi import APIRouter, Depends, HTTPException
from database import conectar_bd
from auth import get_current_user
from models import TokenData
from helpers import _calcular_resumen

router = APIRouter()


@router.get("/turno_actual")
def obtener_turno_actual(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id_turno, estado, fecha_apertura FROM turnos WHERE estado = 'ABIERTO' AND id_tienda = %s LIMIT 1",
                       (user.id_tienda,))
        turno = cursor.fetchone()
        return turno if turno else {"estado": "CERRADO"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/abrir_turno")
def abrir_turno(user: TokenData = Depends(get_current_user)):
    import mysql.connector
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        try:
            cursor.execute(
                "INSERT INTO turnos (estado, id_tienda, turno_activo) VALUES ('ABIERTO', %s, 1)",
                (user.id_tienda,)
            )
            conexion.commit()
            return {"mensaje": "Turno abierto con éxito", "id_turno": cursor.lastrowid}
        except mysql.connector.IntegrityError:
            conexion.rollback()
            cursor.execute(
                "SELECT id_turno FROM turnos WHERE estado='ABIERTO' AND id_tienda=%s LIMIT 1",
                (user.id_tienda,)
            )
            existente = cursor.fetchone()
            return {"mensaje": "Ya hay un turno abierto", "id_turno": existente['id_turno'] if existente else None}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/corte_caja/{id_turno}")
def hacer_corte(id_turno: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)

        conexion.start_transaction()
        # 1. Verificar que el turno existe y está abierto
        cursor.execute(
            "SELECT id_turno FROM turnos WHERE id_turno = %s AND id_tienda = %s AND estado = 'ABIERTO' FOR UPDATE",
            (id_turno, user.id_tienda)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Turno no encontrado o ya cerrado")

        # 2. Calcular primero — si falla, no se cierra nada
        resumen = _calcular_resumen(cursor, id_turno, user.id_tienda)

        # 3. Cerrar solo si el cálculo fue exitoso
        cursor.execute(
            "UPDATE turnos SET fecha_cierre = NOW(), estado = 'CERRADO', turno_activo = NULL WHERE id_turno = %s AND id_tienda = %s",
            (id_turno, user.id_tienda)
        )
        conexion.commit()
        return resumen
    except HTTPException:
        raise
    except Exception as e:
        conexion.rollback()
        raise HTTPException(status_code=500, detail=f"Error al hacer corte: {str(e)}")
    finally:
        if cursor is not None:  # ← proteger el close
            cursor.close()
        conexion.close()


@router.get("/historial_turnos")
def historial_turnos(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_turno, fecha_apertura, fecha_cierre
            FROM turnos WHERE estado = 'CERRADO' AND id_tienda = %s
            ORDER BY fecha_apertura DESC LIMIT 30
        """, (user.id_tienda,))
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.get("/resumen_turno/{id_turno}")
def resumen_turno(id_turno: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        return _calcular_resumen(cursor, id_turno, user.id_tienda)
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.get("/movimientos_turno/{id_turno}")
def obtener_movimientos(id_turno: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_movimiento, cantidad, producto, total_movimiento, tipo_movimiento,
                   TIME_FORMAT(fecha_hora, '%H:%i') as hora
            FROM movimientos
            WHERE id_turno = %s AND id_tienda = %s
            ORDER BY id_movimiento DESC
        """, (id_turno, user.id_tienda))
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        conexion.close()