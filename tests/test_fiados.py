"""
Tests de fiados: saldo, abonos, límite de crédito, aislamiento entre tiendas,
descuento de stock por id_producto (#89) y bugs conocidos (xfail).
"""
import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _cliente(client, caja, nombre="Cliente prueba", limite=None):
    r = client.post("/clientes", headers=caja["headers"],
                    json={"nombre": nombre, "limite_credito": limite})
    assert r.status_code == 200, r.text
    id_cliente = r.json()["id_cliente"]
    cuenta = client.get(f"/cuenta_fiado/{id_cliente}", headers=caja["headers"]).json()
    return id_cliente, cuenta["id_cuenta"]


def _fiar(client, caja, id_cuenta, items, id_turno=None):
    return client.post("/agregar_fiado_lote", headers=caja["headers"], json={
        "id_cuenta": id_cuenta, "id_turno": id_turno or caja["id_turno"], "items": items,
    })


def _abonar(client, caja, id_cuenta, monto, metodo="efectivo", id_turno=None):
    return client.post("/registrar_abono", headers=caja["headers"], json={
        "id_cuenta": id_cuenta, "id_turno": id_turno or caja["id_turno"],
        "monto": monto, "metodo_pago": metodo,
    })


def _item(producto, precio, cantidad=1, id_producto=None):
    d = {"producto": producto, "cantidad": cantidad, "precio": precio}
    if id_producto:
        d["id_producto"] = id_producto
    return d


def _saldo(client, caja, id_cliente):
    return client.get(f"/cuenta_fiado/{id_cliente}", headers=caja["headers"]).json()["saldo"]


def _producto(client, caja, nombre, codigo, stock=10):
    r = client.post("/registrar_producto", headers=caja["headers"], json={
        "codigo_barras": codigo, "nombre_producto": nombre,
        "precio_sugerido": 10, "stock_actual": stock,
    })
    assert r.status_code == 200, r.text
    return r.json()["id_producto"]


def _stock(client, caja, id_producto):
    for p in client.get("/inventario", headers=caja["headers"]).json():
        if p["id_producto"] == id_producto:
            return float(p["stock_actual"])


# ─── Saldo y abonos ───────────────────────────────────────────────────────────
def test_fiado_suma_al_saldo_y_el_abono_lo_baja(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente, id_cuenta = _cliente(client, a)

    assert _fiar(client, a, id_cuenta, [_item("Pan", 60), _item("Leche", 40)]).status_code == 200
    assert _saldo(client, a, id_cliente) == pytest.approx(100)

    r = _abonar(client, a, id_cuenta, 30)
    assert r.status_code == 200, r.text
    assert r.json()["saldo_restante"] == pytest.approx(70)
    assert _saldo(client, a, id_cliente) == pytest.approx(70)


def test_abono_que_salda_la_cuenta_deja_saldo_cero(client, dos_tiendas):
    a = dos_tiendas["a"]
    _, id_cuenta = _cliente(client, a)
    _fiar(client, a, id_cuenta, [_item("Pan", 50)])

    r = _abonar(client, a, id_cuenta, 50)
    assert r.status_code == 200, r.text
    assert r.json()["saldo_restante"] == pytest.approx(0)


def test_fiado_de_producto_que_no_existe_se_registra(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente, id_cuenta = _cliente(client, a)
    r = _fiar(client, a, id_cuenta, [_item("Cosa suelta", 25)])
    assert r.status_code == 200, r.text
    assert _saldo(client, a, id_cliente) == pytest.approx(25)


# ─── Límite de crédito ────────────────────────────────────────────────────────
def test_limite_de_credito_bloquea_fiado_que_lo_excede(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente, id_cuenta = _cliente(client, a, limite=100)

    assert _fiar(client, a, id_cuenta, [_item("Pan", 60)]).status_code == 200
    r = _fiar(client, a, id_cuenta, [_item("Leche", 50)])
    assert r.status_code == 403
    assert _saldo(client, a, id_cliente) == pytest.approx(60)  # no se guardó nada


# ─── Stock en fiados (#89) ────────────────────────────────────────────────────
def test_fiado_con_id_baja_el_stock_del_producto_correcto(client, dos_tiendas):
    a = dos_tiendas["a"]
    _, id_cuenta = _cliente(client, a)
    primero = _producto(client, a, "dup89f", "7500000002001")
    segundo = _producto(client, a, "dup89f", "7500000002002")

    r = _fiar(client, a, id_cuenta, [_item("dup89f", 10, id_producto=segundo)])
    assert r.status_code == 200, r.text
    assert _stock(client, a, primero) == pytest.approx(10)
    assert _stock(client, a, segundo) == pytest.approx(9)


def test_fiado_con_id_de_otra_tienda_no_toca_su_stock(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    _, id_cuenta = _cliente(client, a)
    pid_b = _producto(client, b, "Producto de B", "7500000002003")

    _fiar(client, a, id_cuenta, [_item("Producto de B", 10, id_producto=pid_b)])
    assert _stock(client, b, pid_b) == pytest.approx(10)


# ─── Aislamiento entre tiendas ────────────────────────────────────────────────
def test_no_se_puede_fiar_a_cuenta_de_otra_tienda(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    id_cliente_b, id_cuenta_b = _cliente(client, b, "Cliente de B")

    assert _fiar(client, a, id_cuenta_b, [_item("Pan", 10)]).status_code == 403
    assert _saldo(client, b, id_cliente_b) == pytest.approx(0)


def test_no_se_puede_abonar_a_cuenta_de_otra_tienda(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    _, id_cuenta_b = _cliente(client, b, "Cliente de B")
    assert _abonar(client, a, id_cuenta_b, 10).status_code == 403


def test_abono_con_turno_de_otra_tienda_se_rechaza(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    _, id_cuenta = _cliente(client, a)
    assert _abonar(client, a, id_cuenta, 10, id_turno=b["id_turno"]).status_code == 403


def test_no_se_ve_la_cuenta_de_un_cliente_ajeno(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    id_cliente_b, _ = _cliente(client, b, "Cliente de B")
    r = client.get(f"/cuenta_fiado/{id_cliente_b}", headers=a["headers"])
    assert "error" in r.json()


def test_no_se_puede_editar_cliente_ajeno(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    id_cliente_b, _ = _cliente(client, b, "Cliente de B")

    r = client.put(f"/clientes/{id_cliente_b}/limite_credito", headers=a["headers"],
                   json={"limite_credito": 1})
    assert r.status_code == 404
    r = client.put(f"/clientes/{id_cliente_b}/nombre", headers=a["headers"], json={"nombre": "HACKEADO"})
    assert r.status_code == 404


def test_no_se_puede_eliminar_cliente_ajeno(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    id_cliente_b, _ = _cliente(client, b, "Cliente de B")

    client.delete(f"/clientes/{id_cliente_b}", headers=a["headers"])
    ids_b = [c["id_cliente"] for c in client.get("/clientes", headers=b["headers"]).json()]
    assert id_cliente_b in ids_b


# ─── Eliminar cliente y nombre ────────────────────────────────────────────────
def test_cliente_con_saldo_no_se_puede_eliminar(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente, id_cuenta = _cliente(client, a)
    _fiar(client, a, id_cuenta, [_item("Pan", 50)])

    r = client.delete(f"/clientes/{id_cliente}", headers=a["headers"])
    assert "error" in r.json()
    ids = [c["id_cliente"] for c in client.get("/clientes", headers=a["headers"]).json()]
    assert id_cliente in ids


def test_nombre_de_cliente_no_puede_quedar_vacio(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente, _ = _cliente(client, a)
    r = client.put(f"/clientes/{id_cliente}/nombre", headers=a["headers"], json={"nombre": "   "})
    assert r.status_code == 400


# ─── Bugs conocidos (xfail) ───────────────────────────────────────────────────

def test_abono_mayor_al_saldo_se_rechaza(client, dos_tiendas):
    a = dos_tiendas["a"]
    _, id_cuenta = _cliente(client, a)
    _fiar(client, a, id_cuenta, [_item("Pan", 50)])
    assert _abonar(client, a, id_cuenta, 80).status_code >= 400



def test_cliente_con_saldo_parcial_y_varios_renglones_no_se_elimina(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente, id_cuenta = _cliente(client, a)
    _fiar(client, a, id_cuenta, [_item("Pan", 10), _item("Leche", 10)])
    _abonar(client, a, id_cuenta, 10)  # debe $10

    r = client.delete(f"/clientes/{id_cliente}", headers=a["headers"])
    assert "error" in r.json(), "Se eliminó un cliente que todavía debe $10"



# ─── #91: abonos que exceden el saldo ─────────────────────────────────────────
def test_abono_rechazado_por_exceso_no_deja_rastro_en_saldo_ni_en_caja(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente, id_cuenta = _cliente(client, a)
    _fiar(client, a, id_cuenta, [_item("Pan", 50)])

    r = _abonar(client, a, id_cuenta, 80)

    assert r.status_code == 400
    assert "mayor al saldo" in r.json()["detail"]
    assert _saldo(client, a, id_cliente) == pytest.approx(50)
    resumen = client.get(f"/resumen_turno/{a['id_turno']}", headers=a["headers"]).json()
    assert resumen["total_ingresos"] == pytest.approx(0)


def test_abono_a_cuenta_sin_deuda_se_rechaza(client, dos_tiendas):
    a = dos_tiendas["a"]
    _, id_cuenta = _cliente(client, a)

    r = _abonar(client, a, id_cuenta, 10)

    assert r.status_code == 400
    assert "no tiene saldo" in r.json()["detail"]


def test_abonos_parciales_que_suman_exacto_el_saldo_se_aceptan(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente, id_cuenta = _cliente(client, a)
    _fiar(client, a, id_cuenta, [_item("Pan", 100)])

    assert _abonar(client, a, id_cuenta, 30).status_code == 200
    r = _abonar(client, a, id_cuenta, 70)

    assert r.status_code == 200, r.text
    assert r.json()["saldo_restante"] == pytest.approx(0)


# ─── #90: eliminar cliente con varios renglones y abonos ──────────────────────
def test_cliente_con_deuda_y_varios_renglones_sin_abonos_no_se_elimina(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente, id_cuenta = _cliente(client, a)
    _fiar(client, a, id_cuenta, [_item("Pan", 10), _item("Leche", 10), _item("Huevo", 10)])

    r = client.delete(f"/clientes/{id_cliente}", headers=a["headers"])

    assert "error" in r.json()
    assert "$30.00" in r.json()["error"]


def test_cliente_saldado_con_varios_renglones_y_abonos_si_se_elimina(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente, id_cuenta = _cliente(client, a)
    _fiar(client, a, id_cuenta, [_item("Pan", 10), _item("Leche", 10)])
    assert _abonar(client, a, id_cuenta, 5).status_code == 200
    assert _abonar(client, a, id_cuenta, 15).status_code == 200

    r = client.delete(f"/clientes/{id_cliente}", headers=a["headers"])

    assert r.json().get("mensaje") == "Cliente eliminado"