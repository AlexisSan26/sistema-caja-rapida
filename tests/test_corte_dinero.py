"""
Tests de la lógica de dinero del corte (#100 del roadmap).

Cubren _calcular_resumen (helpers.py) a través de la API real, igual que
test_aislamiento_multitenant.py: efectivo vs tarjeta/transferencia, abonos de
fiado, retiro, fondo, diferencia con efectivo declarado, reglas de deducción,
gastos fijos, snapshot de turno cerrado y el caso real de #88 (tres «cigarros»).

Cada test usa la fixture `dos_tiendas` (tienda nueva + turno abierto), así que
no comparten estado. Solo se usa la tienda "a".

SUPUESTO: movimientos.total_movimiento = cantidad * precio_unitario. Por eso
casi todas las cantidades son 1.
"""
import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _venta(client, caja, items, metodo="efectivo"):
    r = client.post("/registrar_venta_lote", headers=caja["headers"], json={
        "id_turno": caja["id_turno"], "metodo_pago": metodo, "items": items,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _item(nombre, precio, cantidad=1, id_producto=None):
    d = {"producto": nombre, "cantidad": cantidad, "precio_unitario": precio}
    if id_producto:
        d["id_producto"] = id_producto
    return d


def _movimiento(client, caja, tipo, monto):
    r = client.post("/registrar_movimiento", headers=caja["headers"], json={
        "id_turno": caja["id_turno"], "tipo_movimiento": tipo,
        "producto": tipo.title(), "cantidad": 1, "precio_unitario": monto,
    })
    assert r.status_code == 200, r.text


def _config(client, caja, reglas=None, gastos_fijos=None):
    r = client.put("/configuracion_tienda", headers=caja["headers"], json={
        "reglas": reglas or [], "gastos_fijos": gastos_fijos or [],
    })
    assert r.status_code == 200, r.text


def _resumen(client, caja):
    r = client.get(f"/resumen_turno/{caja['id_turno']}", headers=caja["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def _cortar(client, caja, efectivo_declarado=None):
    r = client.post(f"/corte_caja/{caja['id_turno']}", headers=caja["headers"],
                    json={"efectivo_declarado": efectivo_declarado})
    assert r.status_code == 200, r.text
    return r.json()


def _producto_con_codigo(client, caja, nombre, precio, codigo):
    r = client.post("/registrar_producto", headers=caja["headers"], json={
        "codigo_barras": codigo, "nombre_producto": nombre,
        "precio_sugerido": precio, "stock_actual": 10,
    })
    assert r.status_code == 200, r.text
    return r.json()["id_producto"]


# ─── Efectivo vs tarjeta / transferencia (#65) ────────────────────────────────
def test_solo_el_efectivo_cuenta_como_ingreso(client, dos_tiendas):
    a = dos_tiendas["a"]
    _venta(client, a, [_item("Refresco prueba", 100)], "efectivo")
    _venta(client, a, [_item("Galletas prueba", 50)], "tarjeta")
    _venta(client, a, [_item("Dulces prueba", 30)], "transferencia")

    r = _resumen(client, a)
    assert r["total_ingresos"] == pytest.approx(100)
    assert r["total_en_caja"] == pytest.approx(100)
    assert r["pagos_digitales"]["tarjeta"] == {"num_ventas": 1, "total": pytest.approx(50)}
    assert r["pagos_digitales"]["transferencia"] == {"num_ventas": 1, "total": pytest.approx(30)}


def test_abono_de_fiado_en_efectivo_suma_y_en_tarjeta_no(client, dos_tiendas):
    a = dos_tiendas["a"]
    id_cliente = client.post("/clientes", headers=a["headers"],
                             json={"nombre": "Cliente prueba"}).json()["id_cliente"]
    id_cuenta = client.get(f"/cuenta_fiado/{id_cliente}", headers=a["headers"]).json()["id_cuenta"]
    # #91: un abono no puede exceder el saldo, así que primero se fían $100
    r = client.post("/agregar_fiado_lote", headers=a["headers"], json={
        "id_cuenta": id_cuenta, "id_turno": a["id_turno"],
        "items": [{"producto": "Fiado prueba", "cantidad": 1, "precio": 100}],
    })
    assert r.status_code == 200, r.text

    for monto, metodo in ((40, "efectivo"), (25, "tarjeta")):
        r = client.post("/registrar_abono", headers=a["headers"], json={
            "id_cuenta": id_cuenta, "id_turno": a["id_turno"],
            "monto": monto, "metodo_pago": metodo,
        })
        assert r.status_code == 200, r.text

    r = _resumen(client, a)
    assert r["total_ingresos"] == pytest.approx(40)
    assert r["pagos_digitales"]["tarjeta"]["total"] == pytest.approx(25)


# ─── Retiro y fondo ───────────────────────────────────────────────────────────
def test_retiro_resta_y_fondo_no_entra_a_la_caja(client, dos_tiendas):
    a = dos_tiendas["a"]
    _movimiento(client, a, "FONDO_CAJA", 200)
    _venta(client, a, [_item("Venta prueba", 100)])
    _movimiento(client, a, "RETIRO", 30)

    r = _resumen(client, a)
    assert r["total_fondo"] == pytest.approx(200)      # solo informativo
    assert r["total_ingresos"] == pytest.approx(100)   # el fondo no es venta
    assert r["total_retiros"] == pytest.approx(30)
    assert r["total_en_caja"] == pytest.approx(70)     # 100 - 30, sin fondo


# ─── Efectivo declarado y diferencia ──────────────────────────────────────────
def test_corte_con_efectivo_declarado_calcula_diferencia(client, dos_tiendas):
    a = dos_tiendas["a"]
    _venta(client, a, [_item("Venta prueba", 100)])
    _movimiento(client, a, "RETIRO", 20)                # en caja esperado: 80

    r = _cortar(client, a, efectivo_declarado=75)
    assert r["total_en_caja"] == pytest.approx(80)
    assert r["efectivo_real"] == pytest.approx(75)
    assert r["diferencia"] == pytest.approx(-5)         # faltan $5
    assert r["total_neto"] == pytest.approx(75)         # sin deducciones


# ─── Reglas de deducción y gastos fijos ───────────────────────────────────────
def test_regla_de_deduccion_solo_cuenta_ventas_en_efectivo(client, dos_tiendas):
    a = dos_tiendas["a"]
    _config(client, a, reglas=[{"nombre": "Cigarros", "claves": "cigarro", "ids_productos": []}])
    _venta(client, a, [_item("cigarros marlboro", 50)], "efectivo")
    _venta(client, a, [_item("cigarros marlboro", 30)], "tarjeta")

    r = _resumen(client, a)
    assert r["reglas_resumen"]["Cigarros"] == pytest.approx(50)  # la tarjeta no se aparta
    assert r["total_neto"] == pytest.approx(0)                   # 50 en caja - 50 de la regla


def test_gasto_fijo_se_descuenta_completo(client, dos_tiendas):
    a = dos_tiendas["a"]
    _config(client, a, gastos_fijos=[{"nombre": "Renta", "monto": 10}])
    _venta(client, a, [_item("Venta prueba", 100)])

    r = _resumen(client, a)
    assert r["reglas_resumen"]["Renta"] == pytest.approx(10)
    assert r["total_neto"] == pytest.approx(90)


# ─── Turno cerrado con snapshot ───────────────────────────────────────────────
def test_turno_cerrado_no_cambia_si_cambia_la_configuracion(client, dos_tiendas):
    a = dos_tiendas["a"]
    _config(client, a, reglas=[{"nombre": "Cigarros", "claves": "cigarro", "ids_productos": []}])
    _venta(client, a, [_item("cigarros marlboro", 50)])
    _cortar(client, a, efectivo_declarado=50)

    # Mañana cambian las reglas: el turno ya cerrado debe quedar igual
    _config(client, a, reglas=[{"nombre": "Otra regla", "claves": "zzz", "ids_productos": []}],
            gastos_fijos=[{"nombre": "Renta", "monto": 999}])

    r = _resumen(client, a)
    assert r["reglas_resumen"] == {"Cigarros": pytest.approx(50)}
    assert r["total_neto"] == pytest.approx(0)          # 50 declarado - 50 congelado


# ─── Caso real #88: tres productos «cigarros» ─────────────────────────────────
def test_nombres_repetidos_no_duplican_la_deduccion(client, dos_tiendas):
    a = dos_tiendas["a"]
    _producto_con_codigo(client, a, "cigarros", 15, "7500000000011")
    _producto_con_codigo(client, a, "cigarros", 15, "7500000000012")
    id_barato = _producto_con_codigo(client, a, "cigarros", 10, "7500000000013")
    _config(client, a, reglas=[{"nombre": "Cigarros", "claves": "cigarros", "ids_productos": []}])

    _venta(client, a, [_item("cigarros", 10, id_producto=id_barato)])  # con id
    _venta(client, a, [_item("cigarros", 10)])                         # solo por nombre

    r = _resumen(client, a)
    assert r["total_ingresos"] == pytest.approx(20)
    assert r["reglas_resumen"]["Cigarros"] == pytest.approx(20)   # antes del #88 salía triple
    assert r["total_neto"] == pytest.approx(0)                    # y no negativo