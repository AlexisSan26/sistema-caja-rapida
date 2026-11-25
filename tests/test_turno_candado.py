"""
#76 — Una venta/abono/retiro no puede colarse en un turno mientras se hace el corte.

Cómo se simula: una conexión aparte hace lo MISMO que hace hacer_corte() al
empezar (SELECT ... FOR UPDATE sobre la fila del turno) y se queda con la
transacción abierta. Mientras tanto, una venta (en otro hilo) intenta entrar:

  - Sin el fix, la venta lee el turno SIN candado, lo ve ABIERTO, inserta su
    movimiento y termina en menos de 1 s -> el dinero queda en un turno cerrado
    que el corte ya no vio.
  - Con el fix (FOR SHARE), la venta ESPERA a que termine el corte, y al
    destrabarse ve el turno CERRADO y responde 403 sin insertar nada.
"""
import threading
import time
import pytest


def _conexion():
    from database import conectar_bd
    return conectar_bd()


def _simular_corte_en_curso(id_turno):
    """Abre transacción y toma el candado exclusivo del turno, como el corte."""
    con = _conexion()
    cur = con.cursor()
    con.start_transaction()
    cur.execute("SELECT id_turno FROM turnos WHERE id_turno = %s FOR UPDATE", (id_turno,))
    cur.fetchone()
    return con, cur


def _terminar_corte(con, cur, id_turno):
    cur.execute("UPDATE turnos SET estado = 'CERRADO', turno_activo = NULL, fecha_cierre = NOW() WHERE id_turno = %s", (id_turno,))
    con.commit()
    cur.close()
    con.close()


def _contar_movimientos(id_turno):
    con = _conexion()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM movimientos WHERE id_turno = %s", (id_turno,))
    n = cur.fetchone()[0]
    cur.close()
    con.close()
    return n


def _probar_que_espera_y_luego_rechaza(client, caja, peticion):
    """peticion() -> Response. Debe quedarse esperando mientras el corte tiene
    el candado y responder 403 cuando el turno ya quedó cerrado."""
    id_turno = caja["id_turno"]
    con, cur = _simular_corte_en_curso(id_turno)

    resultado = {}
    def _correr():
        resultado["resp"] = peticion()
    hilo = threading.Thread(target=_correr)
    hilo.start()

    time.sleep(1.0)
    seguia_esperando = hilo.is_alive()          # con el fix debe estar bloqueada

    _terminar_corte(con, cur, id_turno)          # el corte termina y cierra el turno
    hilo.join(timeout=10)

    assert seguia_esperando, "La escritura no esperó al corte: entró sin candado sobre el turno"
    assert resultado["resp"].status_code == 403, resultado["resp"].text
    assert _contar_movimientos(id_turno) == 0, "Se coló un movimiento en un turno ya cerrado"


def test_venta_lote_espera_al_corte_y_es_rechazada(client, dos_tiendas):
    a = dos_tiendas["a"]
    _probar_que_espera_y_luego_rechaza(client, a, lambda: client.post(
        "/registrar_venta_lote", headers=a["headers"],
        json={"id_turno": a["id_turno"], "metodo_pago": "efectivo",
              "items": [{"producto": "Pan", "cantidad": 1, "cantidad_real": 1, "precio_unitario": 10}]}))


def test_retiro_espera_al_corte_y_es_rechazado(client, dos_tiendas):
    a = dos_tiendas["a"]
    _probar_que_espera_y_luego_rechaza(client, a, lambda: client.post(
        "/registrar_movimiento", headers=a["headers"],
        json={"id_turno": a["id_turno"], "tipo_movimiento": "RETIRO",
              "producto": "Retiro", "cantidad": 1, "precio_unitario": 50}))


def test_abono_espera_al_corte_y_es_rechazado(client, dos_tiendas):
    a = dos_tiendas["a"]
    r = client.post("/clientes", headers=a["headers"], json={"nombre": "Cliente candado", "limite_credito": None})
    assert r.status_code == 200, r.text
    id_cuenta = client.get(f"/cuenta_fiado/{r.json()['id_cliente']}", headers=a["headers"]).json()["id_cuenta"]
    f = client.post("/agregar_fiado_lote", headers=a["headers"], json={
        "id_cuenta": id_cuenta, "id_turno": a["id_turno"],
        "items": [{"producto": "Pan", "cantidad": 1, "precio": 100}]})
    assert f.status_code == 200, f.text
    antes = _contar_movimientos(a["id_turno"])

    id_turno = a["id_turno"]
    con, cur = _simular_corte_en_curso(id_turno)
    resultado = {}
    hilo = threading.Thread(target=lambda: resultado.update(resp=client.post(
        "/registrar_abono", headers=a["headers"],
        json={"id_cuenta": id_cuenta, "id_turno": id_turno, "monto": 30, "metodo_pago": "efectivo"})))
    hilo.start()
    time.sleep(1.0)
    seguia_esperando = hilo.is_alive()
    _terminar_corte(con, cur, id_turno)
    hilo.join(timeout=10)

    assert seguia_esperando, "El abono no esperó al corte: entró sin candado sobre el turno"
    assert resultado["resp"].status_code == 403, resultado["resp"].text
    assert _contar_movimientos(id_turno) == antes, "Se coló un abono en un turno ya cerrado"