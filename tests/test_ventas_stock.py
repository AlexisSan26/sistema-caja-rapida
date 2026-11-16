"""
Tests de ventas, cancelaciones y stock.

Cubre: descuento de stock por id_producto, cancelar ticket/movimiento (devuelve
stock y quita el ingreso), venta con producto o turno de otra tienda, y el
comportamiento de #89 cuando la venta llega sin id_producto (baja un solo
producto, el de menor id).

xfail = bug conocido del roadmap que todavía no se corrige. Cuando lo corrijas,
el test aparecerá como XPASS: quítale el marcador @pytest.mark.xfail.
"""
import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _producto(client, caja, nombre, codigo, stock=10, precio=10):
    r = client.post("/registrar_producto", headers=caja["headers"], json={
        "codigo_barras": codigo, "nombre_producto": nombre,
        "precio_sugerido": precio, "stock_actual": stock,
    })
    assert r.status_code == 200, r.text
    return r.json()["id_producto"]


def _stock(client, caja, id_producto):
    r = client.get("/inventario", headers=caja["headers"])
    assert r.status_code == 200, r.text
    for p in r.json():
        if p["id_producto"] == id_producto:
            return float(p["stock_actual"])
    return None


def _vender(client, caja, items, metodo="efectivo", id_turno=None):
    return client.post("/registrar_venta_lote", headers=caja["headers"], json={
        "id_turno": id_turno or caja["id_turno"], "metodo_pago": metodo, "items": items,
    })


def _item(nombre, precio=10, cantidad=1, id_producto=None):
    d = {"producto": nombre, "cantidad": cantidad, "precio_unitario": precio}
    if id_producto:
        d["id_producto"] = id_producto
    return d


def _ingresos(client, caja, id_turno=None):
    r = client.get(f"/resumen_turno/{id_turno or caja['id_turno']}", headers=caja["headers"])
    assert r.status_code == 200, r.text
    return r.json()["total_ingresos"]


# ─── Venta y stock ────────────────────────────────────────────────────────────
def test_venta_descuenta_stock_por_id(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Producto venta", "7500000001001", stock=10)

    r = _vender(client, a, [_item("Producto venta", 10, cantidad=3, id_producto=pid)])
    assert r.status_code == 200, r.text
    assert _stock(client, a, pid) == pytest.approx(7)
    assert _ingresos(client, a) == pytest.approx(30)


def test_venta_de_producto_inexistente_lo_da_de_alta(client, dos_tiendas):
    a = dos_tiendas["a"]
    r = _vender(client, a, [_item("Llavero suelto test", 25)])
    assert r.status_code == 200, r.text
    nombres = [p["nombre_producto"] for p in client.get("/inventario", headers=a["headers"]).json()]
    assert "Llavero suelto test" in nombres


def test_venta_con_producto_de_otra_tienda_se_rechaza(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    pid_b = _producto(client, b, "Producto de B", "7500000001002", stock=10)

    r = _vender(client, a, [_item("Producto de B", 10, id_producto=pid_b)])
    assert r.status_code == 400
    assert _stock(client, b, pid_b) == pytest.approx(10)
    assert _ingresos(client, a) == pytest.approx(0)


def test_venta_en_turno_de_otra_tienda_se_rechaza(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    r = _vender(client, a, [_item("Algo", 10)], id_turno=b["id_turno"])
    assert r.status_code == 403
    assert _ingresos(client, b) == pytest.approx(0)


# ─── Cancelaciones ────────────────────────────────────────────────────────────
def test_cancelar_ticket_devuelve_stock_y_quita_el_ingreso(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Producto cancel", "7500000001003", stock=10)
    id_lote = _vender(client, a, [_item("Producto cancel", 10, cantidad=3, id_producto=pid)]).json()["id_lote"]
    assert _stock(client, a, pid) == pytest.approx(7)

    r = client.delete(f"/borrar_lote/{id_lote}", headers=a["headers"])
    assert r.status_code == 200, r.text
    assert _stock(client, a, pid) == pytest.approx(10)
    assert _ingresos(client, a) == pytest.approx(0)


def test_cancelar_movimiento_suelto_devuelve_stock(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Producto mov", "7500000001004", stock=10)
    _vender(client, a, [_item("Producto mov", 10, cantidad=2, id_producto=pid)])
    movs = client.get(f"/movimientos_turno/{a['id_turno']}", headers=a["headers"]).json()
    id_mov = next(m["id_movimiento"] for m in movs if m["tipo_movimiento"] == "VENTA")

    r = client.delete(f"/borrar_movimiento/{id_mov}", headers=a["headers"])
    assert r.status_code == 200, r.text
    assert _stock(client, a, pid) == pytest.approx(10)
    assert _ingresos(client, a) == pytest.approx(0)


def test_no_se_puede_cancelar_ticket_de_otra_tienda(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    pid = _producto(client, a, "Producto de A", "7500000001005", stock=10)
    id_lote = _vender(client, a, [_item("Producto de A", 10, cantidad=3, id_producto=pid)]).json()["id_lote"]

    client.delete(f"/borrar_lote/{id_lote}", headers=b["headers"])  # B intenta cancelar el de A

    assert _stock(client, a, pid) == pytest.approx(7)
    assert _ingresos(client, a) == pytest.approx(30)


# ─── #89: venta sin id_producto y nombres repetidos ───────────────────────────
def test_venta_sin_id_baja_solo_el_producto_de_menor_id(client, dos_tiendas):
    a = dos_tiendas["a"]
    primero = _producto(client, a, "dup89", "7500000001011", stock=10)
    segundo = _producto(client, a, "dup89", "7500000001012", stock=10)
    assert primero < segundo

    id_lote = _vender(client, a, [_item("dup89", 10)]).json()["id_lote"]  # sin id_producto
    assert _stock(client, a, primero) == pytest.approx(9)
    assert _stock(client, a, segundo) == pytest.approx(10)  # el otro no se toca

    client.delete(f"/borrar_lote/{id_lote}", headers=a["headers"])
    assert _stock(client, a, primero) == pytest.approx(10)
    assert _stock(client, a, segundo) == pytest.approx(10)


def test_venta_con_id_baja_el_producto_correcto_aunque_haya_homonimos(client, dos_tiendas):
    a = dos_tiendas["a"]
    primero = _producto(client, a, "dup89b", "7500000001013", stock=10)
    segundo = _producto(client, a, "dup89b", "7500000001014", stock=10)

    _vender(client, a, [_item("dup89b", 10, id_producto=segundo)])
    assert _stock(client, a, primero) == pytest.approx(10)
    assert _stock(client, a, segundo) == pytest.approx(9)


# ─── Bugs conocidos (xfail) ───────────────────────────────────────────────────
@pytest.mark.xfail(strict=False, reason="#64: se puede borrar un movimiento de un turno ya cerrado")
def test_no_se_puede_borrar_movimiento_de_turno_cerrado(client, dos_tiendas):
    a = dos_tiendas["a"]
    _vender(client, a, [_item("Venta antes del corte", 10)])
    r = client.post(f"/corte_caja/{a['id_turno']}", headers=a["headers"], json={"efectivo_declarado": 10})
    assert r.status_code == 200, r.text
    movs = client.get(f"/movimientos_turno/{a['id_turno']}", headers=a["headers"]).json()
    id_mov = movs[0]["id_movimiento"]

    r = client.delete(f"/borrar_movimiento/{id_mov}", headers=a["headers"])
    assert r.status_code >= 400, "Se permitió borrar un movimiento de un turno CERRADO"