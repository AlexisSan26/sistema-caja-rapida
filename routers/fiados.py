from fastapi import APIRouter, Depends, HTTPException
from database import conectar_bd
from auth import get_current_user
from models import TokenData, ClienteNuevo, ItemFiado, AbonoFiado

router = APIRouter()


@router.get("/clientes")
def listar_clientes(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.id_cliente, c.nombre, c.telefono,
                   COALESCE(
                     (SELECT SUM(df.cantidad * df.precio)
                      FROM detalle_fiado df
                      JOIN cuentas_fiado cf ON df.id_cuenta = cf.id_cuenta
                      WHERE cf.id_cliente = c.id_cliente AND cf.estado = 'ABIERTA' AND df.id_tienda = %s)
                   , 0) -
                   COALESCE(
                     (SELECT SUM(a.monto)
                      FROM abonos a
                      JOIN cuentas_fiado cf ON a.id_cuenta = cf.id_cuenta
                      WHERE cf.id_cliente = c.id_cliente AND cf.estado = 'ABIERTA' AND a.id_tienda = %s)
                   , 0) AS saldo_actual
            FROM clientes c
            WHERE c.activo = 1 AND c.id_tienda = %s
            ORDER BY c.nombre ASC
        """, (user.id_tienda, user.id_tienda, user.id_tienda))
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/clientes")
def crear_cliente(c: ClienteNuevo, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO clientes (nombre, telefono, id_tienda) VALUES (%s, %s, %s)",
            (c.nombre.strip(), c.telefono or None, user.id_tienda)
        )
        id_cliente = cursor.lastrowid
        cursor.execute(
            "INSERT INTO cuentas_fiado (id_cliente, id_tienda) VALUES (%s, %s)",
            (id_cliente, user.id_tienda)
        )
        conexion.commit()
        return {"mensaje": "Cliente registrado", "id_cliente": id_cliente}
    except HTTPException:
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear cliente: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.delete("/clientes/{id_cliente}")
def eliminar_cliente(id_cliente: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT COALESCE(SUM(df.cantidad * df.precio), 0) - COALESCE(SUM(a.monto), 0) AS saldo
            FROM cuentas_fiado cf
            LEFT JOIN detalle_fiado df ON df.id_cuenta = cf.id_cuenta
            LEFT JOIN abonos a ON a.id_cuenta = cf.id_cuenta
            WHERE cf.id_cliente = %s AND cf.estado = 'ABIERTA' AND cf.id_tienda = %s
        """, (id_cliente, user.id_tienda))
        row = cursor.fetchone()
        if row and float(row["saldo"]) != 0:
            return {"error": f"El cliente tiene saldo pendiente de ${float(row['saldo']):.2f}. Salda la cuenta antes."}
        cursor.execute("UPDATE clientes SET activo = 0 WHERE id_cliente = %s AND id_tienda = %s",
                       (id_cliente, user.id_tienda))
        conexion.commit()
        return {"mensaje": "Cliente eliminado"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.get("/cuenta_fiado/{id_cliente}")
def obtener_cuenta(id_cliente: int, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_cliente, nombre, telefono FROM clientes WHERE id_cliente = %s AND activo = 1 AND id_tienda = %s",
            (id_cliente, user.id_tienda)
        )
        cliente = cursor.fetchone()
        if not cliente:
            return {"error": "Cliente no encontrado"}

        cursor.execute(
            "SELECT id_cuenta FROM cuentas_fiado WHERE id_cliente = %s AND estado = 'ABIERTA' AND id_tienda = %s LIMIT 1",
            (id_cliente, user.id_tienda)
        )
        cuenta = cursor.fetchone()
        if not cuenta:
            cursor.execute("INSERT INTO cuentas_fiado (id_cliente, id_tienda) VALUES (%s, %s)",
                           (id_cliente, user.id_tienda))
            conexion.commit()
            id_cuenta = cursor.lastrowid
        else:
            id_cuenta = cuenta['id_cuenta']

        cursor.execute("""
            SELECT producto, cantidad, precio, (cantidad * precio) AS subtotal,
                   DATE_FORMAT(fecha_hora, '%d/%m %H:%i') as fecha
            FROM detalle_fiado WHERE id_cuenta = %s AND id_tienda = %s
            ORDER BY fecha_hora ASC
        """, (id_cuenta, user.id_tienda))
        detalle = cursor.fetchall()

        cursor.execute("""
            SELECT monto, nota, DATE_FORMAT(fecha_hora, '%d/%m %H:%i') as fecha
            FROM abonos WHERE id_cuenta = %s AND id_tienda = %s
            ORDER BY fecha_hora ASC
        """, (id_cuenta, user.id_tienda))
        abonos = cursor.fetchall()

        total_fiado = sum(float(d['subtotal']) for d in detalle)
        total_abonos = sum(float(a['monto']) for a in abonos)
        saldo = total_fiado - total_abonos

        return {
            "cliente": cliente,
            "id_cuenta": id_cuenta,
            "detalle": detalle,
            "abonos": abonos,
            "total_fiado": total_fiado,
            "total_abonos": total_abonos,
            "saldo": saldo
        }
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.post("/agregar_fiado")
def agregar_fiado(item: ItemFiado, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()

        # ── Transacción explícita + lock de fila ──────────────────────────────
        # FOR UPDATE en cuentas_fiado evita que dos requests simultáneos
        # descuenten stock y agreguen detalle sobre la misma cuenta al mismo tiempo.
        conexion.start_transaction()

        cursor.execute("""
            SELECT cf.id_cuenta FROM cuentas_fiado cf
            JOIN clientes c ON c.id_cliente = cf.id_cliente
            WHERE cf.id_cuenta = %s AND c.id_tienda = %s AND cf.estado = 'ABIERTA'
            FOR UPDATE
        """, (item.id_cuenta, user.id_tienda))
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Cuenta de fiado no válida para esta tienda")

        cursor.execute("""
            INSERT INTO detalle_fiado (id_cuenta, producto, cantidad, precio, id_tienda)
            VALUES (%s, %s, %s, %s, %s)
        """, (item.id_cuenta, item.producto.strip(), item.cantidad, item.precio, user.id_tienda))

        cursor.execute("""
            UPDATE productos SET stock_actual = stock_actual - %s
            WHERE nombre_producto = %s AND activo = 1 AND id_tienda = %s
        """, (float(item.cantidad), item.producto.strip(), user.id_tienda))

        conexion.commit()  # ← libera el FOR UPDATE lock
        return {"mensaje": "Fiado registrado correctamente"}
    except HTTPException:
        if conexion:
            conexion.rollback()
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar fiado: {str(e)}")
    finally:
        if cursor is not None:
            cursor.close()
        conexion.close()


@router.post("/registrar_abono")
def registrar_abono(abono: AbonoFiado, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)

        # ── Transacción explícita + lock de fila ──────────────────────────────
        # SELECT FOR UPDATE bloquea esta cuenta_fiado específica hasta el commit.
        # Si dos cajeros intentan abonar a la misma cuenta al mismo tiempo,
        # el segundo esperará en esta línea hasta que el primero haga commit.
        conexion.start_transaction()

        cursor.execute("""
            SELECT cf.id_cuenta, c.nombre FROM cuentas_fiado cf
            JOIN clientes c ON c.id_cliente = cf.id_cliente
            WHERE cf.id_cuenta = %s AND cf.id_tienda = %s
            FOR UPDATE
        """, (abono.id_cuenta, user.id_tienda))
        res = cursor.fetchone()
        if not res:
            raise HTTPException(status_code=403, detail="Cuenta de fiado no válida para esta tienda")
        nombre_cliente = res['nombre']

        # Validar que el turno pertenece a esta tienda
        cursor.execute(
            "SELECT id_turno FROM turnos WHERE id_turno = %s AND id_tienda = %s AND estado = 'ABIERTO'",
            (abono.id_turno, user.id_tienda)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Turno no válido para esta tienda")

        cursor.execute(
            "INSERT INTO abonos (id_cuenta, monto, nota, id_tienda) VALUES (%s, %s, %s, %s)",
            (abono.id_cuenta, abono.monto, abono.nota or None, user.id_tienda)
        )
        cursor.execute("""
            INSERT INTO movimientos (id_turno, tipo_movimiento, producto, cantidad, precio_unitario, id_tienda)
            VALUES (%s, 'COBRO_FIADO', %s, 1, %s, %s)
        """, (abono.id_turno, f"Abono fiado — {nombre_cliente}", abono.monto, user.id_tienda))

        # Estos SELECTs ahora son seguros: nadie más puede modificar esta
        # cuenta hasta que el commit de abajo libere el FOR UPDATE lock.
        cursor.execute("""
            SELECT COALESCE(SUM(df.cantidad * df.precio), 0) AS total_fiado
            FROM detalle_fiado df WHERE df.id_cuenta = %s AND df.id_tienda = %s
        """, (abono.id_cuenta, user.id_tienda))
        tf = cursor.fetchone()

        cursor.execute(
            "SELECT COALESCE(SUM(monto), 0) AS total_abonos FROM abonos WHERE id_cuenta = %s AND id_tienda = %s",
            (abono.id_cuenta, user.id_tienda)
        )
        ta = cursor.fetchone()

        saldo_nuevo = float(tf['total_fiado']) - float(ta['total_abonos'])
        if saldo_nuevo <= 0:  # <= 0 cubre también el caso de pago con cambio
            cursor.execute(
                "UPDATE cuentas_fiado SET estado = 'SALDADA' WHERE id_cuenta = %s AND id_tienda = %s",
                (abono.id_cuenta, user.id_tienda)
            )
        conexion.commit()  # ← libera el FOR UPDATE lock
        return {
            "mensaje": "Abono registrado",
            "saldo_restante": max(0.0, saldo_nuevo),
            "saldo_favor": abs(min(0.0, saldo_nuevo))
        }
    except HTTPException:
        if conexion:
            conexion.rollback()
        raise
    except Exception as e:
        if conexion:
            conexion.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar abono: {str(e)}")
    finally:
        if cursor is not None:
            cursor.close()
        conexion.close()