"""
Tests de idempotencia (#66): un reintento con la misma Idempotency-Key no duplica
la venta, ni el ingreso, ni el descuento de stock.
"""
import threading
import pytest


def _producto(client, caja, nombre, codigo, stock=10, precio=10):
    r = client.post("/registrar_producto", headers=caja["headers"], json={
        "codigo_barras": codigo, "nombre_producto": nombre,
        "precio_sugerido": precio, "stock_actual": stock,
    })
    assert r.status_code == 200, r.text
    return r.json()["id_producto"]


def _stock(client, caja, id_producto):
    r = client.get("/inventario", headers=caja["headers"])
    return next(float(p["stock_actual"]) for p in r.json() if p["id_producto"] == id_producto)


def _ingresos(client, caja):
    r = client.get(f"/resumen_turno/{caja['id_turno']}", headers=caja["headers"])
    assert r.status_code == 200, r.text
    return r.json()["total_ingresos"]


def _vender(client, caja, pid, clave=None, id_turno=None):
    headers = dict(caja["headers"])
    if clave:
        headers["Idempotency-Key"] = clave
    return client.post("/registrar_venta_lote", headers=headers, json={
        "id_turno": id_turno or caja["id_turno"], "metodo_pago": "efectivo",
        "items": [{"producto": "Prod idem", "cantidad": 1, "precio_unitario": 10, "id_producto": pid}],
    })


def test_reintento_con_misma_clave_no_duplica_la_venta(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066001", stock=10)

    r1 = _vender(client, a, pid, clave="clave-venta-0001")
    r2 = _vender(client, a, pid, clave="clave-venta-0001")

    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["id_lote"] == r1.json()["id_lote"]
    assert r2.json().get("repetido") is True
    assert r1.json().get("repetido") is None
    assert _ingresos(client, a) == pytest.approx(10)
    assert _stock(client, a, pid) == pytest.approx(9)


def test_claves_distintas_son_ventas_distintas(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066002", stock=10)

    assert _vender(client, a, pid, clave="clave-venta-0002").status_code == 200
    assert _vender(client, a, pid, clave="clave-venta-0003").status_code == 200

    assert _ingresos(client, a) == pytest.approx(20)
    assert _stock(client, a, pid) == pytest.approx(8)


def test_sin_clave_sigue_funcionando_como_antes(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066003", stock=10)

    assert _vender(client, a, pid).status_code == 200
    assert _vender(client, a, pid).status_code == 200

    assert _ingresos(client, a) == pytest.approx(20)


def test_misma_clave_en_otra_tienda_no_colisiona(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    pid_a = _producto(client, a, "Prod idem", "7500000066004", stock=10)
    pid_b = _producto(client, b, "Prod idem", "7500000066005", stock=10)

    assert _vender(client, a, pid_a, clave="clave-compartida-01").status_code == 200
    rb = _vender(client, b, pid_b, clave="clave-compartida-01")

    assert rb.status_code == 200
    assert rb.json().get("repetido") is None
    assert _ingresos(client, b) == pytest.approx(10)


def test_venta_rechazada_no_consume_la_clave(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    pid = _producto(client, a, "Prod idem", "7500000066006", stock=10)

    # Primer intento: turno de otra tienda → 403, nada se guarda
    r1 = _vender(client, a, pid, clave="clave-venta-0004", id_turno=b["id_turno"])
    assert r1.status_code == 403

    # Reintento corregido con la misma clave → se registra normal
    r2 = _vender(client, a, pid, clave="clave-venta-0004")
    assert r2.status_code == 200
    assert r2.json().get("repetido") is None
    assert _ingresos(client, a) == pytest.approx(10)


def test_dos_peticiones_simultaneas_con_la_misma_clave_registran_una_sola_venta(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066007", stock=10)
    resultados = []

    def _enviar():
        resultados.append(_vender(client, a, pid, clave="clave-simultanea-01"))

    hilos = [threading.Thread(target=_enviar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert [r.status_code for r in resultados] == [200, 200]
    assert len({r.json()["id_lote"] for r in resultados}) == 1
    assert _ingresos(client, a) == pytest.approx(10)
    assert _stock(client, a, pid) == pytest.approx(9)

def test_misma_clave_con_contenido_distinto_es_409(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066008", stock=10)

    assert _vender(client, a, pid, clave="clave-venta-0009").status_code == 200
    headers = dict(a["headers"]); headers["Idempotency-Key"] = "clave-venta-0009"
    r = client.post("/registrar_venta_lote", headers=headers, json={
        "id_turno": a["id_turno"], "metodo_pago": "tarjeta",
        "items": [{"producto": "Prod idem", "cantidad": 1, "precio_unitario": 10, "id_producto": pid}],
    })
    assert r.status_code == 409
    assert _ingresos(client, a) == pytest.approx(10)
    assert _stock(client, a, pid) == pytest.approx(9)



# ─── /registrar_movimiento: retiros y fondo de caja ───────────────────────────
def _movimiento(client, caja, tipo, monto, concepto, clave=None):
    headers = dict(caja["headers"])
    if clave:
        headers["Idempotency-Key"] = clave
    return client.post("/registrar_movimiento", headers=headers, json={
        "id_turno": caja["id_turno"], "tipo_movimiento": tipo,
        "producto": concepto, "cantidad": 1, "precio_unitario": monto,
    })


def _campo_resumen(client, caja, campo):
    r = client.get(f"/resumen_turno/{caja['id_turno']}", headers=caja["headers"])
    assert r.status_code == 200, r.text
    return r.json()[campo]


def test_reintento_de_retiro_con_misma_clave_no_duplica(client, dos_tiendas):
    a = dos_tiendas["a"]
    antes = _campo_resumen(client, a, "total_retiros")

    r1 = _movimiento(client, a, "RETIRO", 50, "Gasolina", clave="clave-ret-0001")
    r2 = _movimiento(client, a, "RETIRO", 50, "Gasolina", clave="clave-ret-0001")

    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json().get("repetido") is True
    assert r1.json().get("repetido") is None
    assert _campo_resumen(client, a, "total_retiros") == pytest.approx(antes + 50)


def test_reintento_de_fondo_con_misma_clave_no_duplica(client, dos_tiendas):
    a = dos_tiendas["a"]
    antes = _campo_resumen(client, a, "total_fondo")

    assert _movimiento(client, a, "FONDO_CAJA", 200, "Fondo inicial", clave="clave-fondo-0001").status_code == 200
    assert _movimiento(client, a, "FONDO_CAJA", 200, "Fondo inicial", clave="clave-fondo-0001").status_code == 200

    assert _campo_resumen(client, a, "total_fondo") == pytest.approx(antes + 200)


def test_retiro_misma_clave_con_otro_monto_es_409(client, dos_tiendas):
    a = dos_tiendas["a"]
    antes = _campo_resumen(client, a, "total_retiros")

    assert _movimiento(client, a, "RETIRO", 50, "Gasolina", clave="clave-ret-0002").status_code == 200
    r = _movimiento(client, a, "RETIRO", 80, "Gasolina", clave="clave-ret-0002")

    assert r.status_code == 409
    assert _campo_resumen(client, a, "total_retiros") == pytest.approx(antes + 50)


def test_clave_de_venta_no_se_puede_reusar_en_un_retiro(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066009", stock=10)
    antes = _campo_resumen(client, a, "total_retiros")

    assert _vender(client, a, pid, clave="clave-cruzada-01").status_code == 200
    r = _movimiento(client, a, "RETIRO", 10, "Gasolina", clave="clave-cruzada-01")

    assert r.status_code == 409
    assert _campo_resumen(client, a, "total_retiros") == pytest.approx(antes)


def test_retiro_rechazado_no_consume_la_clave(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    antes = _campo_resumen(client, a, "total_retiros")
    headers = dict(a["headers"]); headers["Idempotency-Key"] = "clave-ret-0003"

    r1 = client.post("/registrar_movimiento", headers=headers, json={
        "id_turno": b["id_turno"], "tipo_movimiento": "RETIRO",
        "producto": "Gasolina", "cantidad": 1, "precio_unitario": 50})
    assert r1.status_code == 403

    r2 = _movimiento(client, a, "RETIRO", 50, "Gasolina", clave="clave-ret-0003")
    assert r2.status_code == 200 and r2.json().get("repetido") is None
    assert _campo_resumen(client, a, "total_retiros") == pytest.approx(antes + 50)



# ─── /agregar_fiado_lote ──────────────────────────────────────────────────────
def _cuenta_fiado(client, caja, nombre="Cliente idem", limite=None):
    r = client.post("/clientes", headers=caja["headers"], json={"nombre": nombre, "limite_credito": limite})
    assert r.status_code == 200, r.text
    id_cliente = r.json()["id_cliente"]
    cuenta = client.get(f"/cuenta_fiado/{id_cliente}", headers=caja["headers"]).json()
    return id_cliente, cuenta["id_cuenta"]


def _saldo_fiado(client, caja, id_cliente):
    return client.get(f"/cuenta_fiado/{id_cliente}", headers=caja["headers"]).json()["saldo"]


def _fiar(client, caja, id_cuenta, items, clave=None):
    headers = dict(caja["headers"])
    if clave:
        headers["Idempotency-Key"] = clave
    return client.post("/agregar_fiado_lote", headers=headers, json={
        "id_cuenta": id_cuenta, "id_turno": caja["id_turno"], "items": items})


def _item_fiado(pid, precio=10, cantidad=1):
    return {"producto": "Prod idem", "cantidad": cantidad, "precio": precio, "id_producto": pid}


def test_reintento_de_fiado_con_misma_clave_no_duplica_deuda_ni_stock(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066010", stock=10)
    id_cliente, id_cuenta = _cuenta_fiado(client, a)

    r1 = _fiar(client, a, id_cuenta, [_item_fiado(pid)], clave="clave-fiado-0001")
    r2 = _fiar(client, a, id_cuenta, [_item_fiado(pid)], clave="clave-fiado-0001")

    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json().get("repetido") is True
    assert r1.json().get("repetido") is None
    assert _saldo_fiado(client, a, id_cliente) == pytest.approx(10)
    assert _stock(client, a, pid) == pytest.approx(9)


def test_fiado_misma_clave_con_otro_contenido_es_409(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066011", stock=10)
    id_cliente, id_cuenta = _cuenta_fiado(client, a)

    assert _fiar(client, a, id_cuenta, [_item_fiado(pid, precio=10)], clave="clave-fiado-0002").status_code == 200
    r = _fiar(client, a, id_cuenta, [_item_fiado(pid, precio=99)], clave="clave-fiado-0002")

    assert r.status_code == 409
    assert _saldo_fiado(client, a, id_cliente) == pytest.approx(10)


def test_reintento_de_fiado_ya_registrado_no_se_rechaza_por_limite_de_credito(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066012", stock=10)
    id_cliente, id_cuenta = _cuenta_fiado(client, a, limite=15)

    assert _fiar(client, a, id_cuenta, [_item_fiado(pid)], clave="clave-fiado-0003").status_code == 200
    # Un fiado NUEVO de $10 ya no cabe (10 + 10 > 15), pero el REINTENTO del primero debe responder igual
    r = _fiar(client, a, id_cuenta, [_item_fiado(pid)], clave="clave-fiado-0003")

    assert r.status_code == 200 and r.json().get("repetido") is True
    assert _saldo_fiado(client, a, id_cliente) == pytest.approx(10)


def test_fiado_rechazado_no_consume_la_clave(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    pid = _producto(client, a, "Prod idem", "7500000066013", stock=10)
    id_cliente, id_cuenta = _cuenta_fiado(client, a)
    _, id_cuenta_b = _cuenta_fiado(client, b, nombre="Cliente de B")

    assert _fiar(client, a, id_cuenta_b, [_item_fiado(pid)], clave="clave-fiado-0004").status_code == 403
    r = _fiar(client, a, id_cuenta, [_item_fiado(pid)], clave="clave-fiado-0004")

    assert r.status_code == 200 and r.json().get("repetido") is None
    assert _saldo_fiado(client, a, id_cliente) == pytest.approx(10)


def test_clave_de_venta_no_se_puede_reusar_en_un_fiado(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066014", stock=10)
    id_cliente, id_cuenta = _cuenta_fiado(client, a)

    assert _vender(client, a, pid, clave="clave-cruzada-02").status_code == 200
    r = _fiar(client, a, id_cuenta, [_item_fiado(pid)], clave="clave-cruzada-02")

    assert r.status_code == 409
    assert _saldo_fiado(client, a, id_cliente) == pytest.approx(0)
    assert _stock(client, a, pid) == pytest.approx(9)


def test_dos_fiados_simultaneos_con_la_misma_clave_registran_uno_solo(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Prod idem", "7500000066015", stock=10)
    id_cliente, id_cuenta = _cuenta_fiado(client, a)
    resultados = []

    def _enviar():
        resultados.append(_fiar(client, a, id_cuenta, [_item_fiado(pid)], clave="clave-fiado-simultanea"))

    hilos = [threading.Thread(target=_enviar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert [r.status_code for r in resultados] == [200, 200]
    assert _saldo_fiado(client, a, id_cliente) == pytest.approx(10)
    assert _stock(client, a, pid) == pytest.approx(9)