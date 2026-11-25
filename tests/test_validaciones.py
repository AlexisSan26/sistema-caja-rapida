"""
#68 — Validaciones de entrada (Pydantic). El servidor rechaza datos sin sentido
antes de tocar la base, porque el corte depende de estos valores.
"""


def _venta(client, caja, metodo="efectivo", precio=10, cantidad=1):
    return client.post("/registrar_venta_lote", headers=caja["headers"], json={
        "id_turno": caja["id_turno"], "metodo_pago": metodo,
        "items": [{"producto": "Pan", "cantidad": cantidad, "precio_unitario": precio}],
    })


def test_metodo_pago_desconocido_se_rechaza(client, dos_tiendas):
    a = dos_tiendas["a"]
    assert _venta(client, a, metodo="tarjta").status_code == 422
    assert _venta(client, a, metodo="Efectivo").status_code == 422


def test_metodos_validos_se_aceptan(client, dos_tiendas):
    a = dos_tiendas["a"]
    for metodo in ("efectivo", "tarjeta", "transferencia"):
        assert _venta(client, a, metodo=metodo).status_code == 200


def test_precio_o_cantidad_negativos_se_rechazan(client, dos_tiendas):
    a = dos_tiendas["a"]
    assert _venta(client, a, precio=-5).status_code == 422
    assert _venta(client, a, cantidad=-1).status_code == 422


def test_precio_cero_sigue_permitido(client, dos_tiendas):
    a = dos_tiendas["a"]
    assert _venta(client, a, precio=0).status_code == 200


def test_abono_con_metodo_desconocido_se_rechaza(client, dos_tiendas):
    a = dos_tiendas["a"]
    r = client.post("/registrar_abono", headers=a["headers"], json={
        "id_cuenta": 1, "id_turno": a["id_turno"], "monto": 10, "metodo_pago": "cheque"})
    assert r.status_code == 422


def test_corte_con_efectivo_declarado_negativo_no_cierra_el_turno(client, dos_tiendas):
    a = dos_tiendas["a"]
    r = client.post(f"/corte_caja/{a['id_turno']}", headers=a["headers"],
                    json={"efectivo_declarado": -50})
    assert r.status_code == 422
    # el turno sigue abierto: un corte válido después sí funciona
    r2 = client.post(f"/corte_caja/{a['id_turno']}", headers=a["headers"],
                     json={"efectivo_declarado": 0})
    assert r2.status_code == 200, r2.text