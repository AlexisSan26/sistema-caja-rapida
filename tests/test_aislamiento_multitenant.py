"""
Roadmap #12 — "Al menos un test automatizado de aislamiento multi-tenant"
(marcado en el roadmap como la inversión de mayor apalancamiento).

Cada test simula 2 tiendas reales (A y B) operando en paralelo y verifica que
la tienda A NUNCA pueda ver, modificar ni borrar datos de la tienda B — ni
por listados, ni adivinando IDs (IDOR).

Si un test de este archivo falla, es señal de una fuga real entre tenants:
trátalo como el bug de mayor prioridad posible, por encima de cualquier
feature nueva.
"""


def test_productos_no_se_mezclan_entre_tiendas(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]

    client.post("/registrar_producto", headers=a["headers"],
                json={"nombre_producto": "Producto exclusivo A", "precio_sugerido": 10})
    client.post("/registrar_producto", headers=b["headers"],
                json={"nombre_producto": "Producto exclusivo B", "precio_sugerido": 20})

    productos_a = client.get("/productos", headers=a["headers"]).json()
    productos_b = client.get("/productos", headers=b["headers"]).json()

    nombres_a = {p["nombre_producto"] for p in productos_a}
    nombres_b = {p["nombre_producto"] for p in productos_b}

    assert "Producto exclusivo A" in nombres_a
    assert "Producto exclusivo B" not in nombres_a, "¡Tienda A ve un producto de Tienda B!"

    assert "Producto exclusivo B" in nombres_b
    assert "Producto exclusivo A" not in nombres_b, "¡Tienda B ve un producto de Tienda A!"


def test_no_se_puede_editar_producto_de_otra_tienda(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]

    resp = client.post("/registrar_producto", headers=b["headers"],
                       json={"nombre_producto": "Original de B", "precio_sugerido": 15})
    id_producto_b = resp.json()["id_producto"]

    # A intenta editar un producto que sabe que existe (adivinando el ID) pero es de B
    client.put(f"/actualizar_producto/{id_producto_b}", headers=a["headers"], json={
        "nombre_producto": "HACKEADO POR A",
        "precio_sugerido": 999, "precio_costo": None,
        "stock_actual": 0, "stock_minimo": 0,
        "proveedor": None, "codigo_barras": None,
        "fecha_caducidad": None, "unidad_medida": "pieza",
    })

    # El producto de B debe seguir intacto
    productos_b = client.get("/productos", headers=b["headers"]).json()
    prod = next(p for p in productos_b if p["id_producto"] == id_producto_b)
    assert prod["nombre_producto"] == "Original de B", "¡Tienda A pudo modificar un producto de Tienda B!"


def test_no_se_puede_borrar_producto_de_otra_tienda(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]

    resp = client.post("/registrar_producto", headers=b["headers"],
                       json={"nombre_producto": "No debe borrarse", "precio_sugerido": 5})
    id_producto_b = resp.json()["id_producto"]

    client.delete(f"/eliminar_producto/{id_producto_b}", headers=a["headers"])

    productos_b = client.get("/productos", headers=b["headers"]).json()
    ids_b = {p["id_producto"] for p in productos_b}
    assert id_producto_b in ids_b, "¡Tienda A pudo archivar/borrar un producto de Tienda B!"


def test_descontar_stock_de_producto_ajeno_da_404(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]

    resp = client.post("/registrar_producto", headers=b["headers"],
                       json={"nombre_producto": "Stock de B", "precio_sugerido": 5, "stock_actual": 100})
    id_producto_b = resp.json()["id_producto"]

    resp = client.post(f"/descontar_stock/{id_producto_b}", headers=a["headers"], params={"cantidad": 50})
    assert resp.status_code == 404

    productos_b = client.get("/productos", headers=b["headers"]).json()
    prod = next(p for p in productos_b if p["id_producto"] == id_producto_b)
    # Confirmamos que el stock de B no se movió consultando el inventario completo
    inventario_b = client.get("/inventario", headers=b["headers"]).json()
    inv = next(p for p in inventario_b if p["id_producto"] == id_producto_b)
    assert inv["stock_actual"] == 100, "¡Tienda A pudo descontar stock de un producto de Tienda B!"


def test_turnos_y_movimientos_no_se_mezclan(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]

    client.post("/registrar_movimiento", headers=b["headers"], json={
        "id_turno": b["id_turno"], "tipo_movimiento": "VENTA",
        "producto": "Venta secreta de B", "cantidad": 1, "precio_unitario": 500,
    })

    # A intenta leer el turno de B directamente por ID
    movs = client.get(f"/movimientos_turno/{b['id_turno']}", headers=a["headers"]).json()
    assert movs == [], "¡Tienda A pudo leer los movimientos del turno de Tienda B!"

    # A intenta hacer el corte de caja del turno de B
    resp = client.post(f"/corte_caja/{b['id_turno']}", headers=a["headers"])
    assert resp.status_code == 404, "¡Tienda A pudo intentar el corte de un turno de Tienda B!"

    # El turno de B debe seguir abierto pase lo que pase
    turno_actual_b = client.get("/turno_actual", headers=b["headers"]).json()
    assert turno_actual_b.get("estado") == "ABIERTO", "¡El intento de corte de A afectó el turno real de B!"


def test_no_se_puede_borrar_movimiento_de_otra_tienda(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]

    client.post("/registrar_movimiento", headers=b["headers"], json={
        "id_turno": b["id_turno"], "tipo_movimiento": "VENTA",
        "producto": "No debe cancelarse", "cantidad": 1, "precio_unitario": 30,
    })
    movs_b = client.get(f"/movimientos_turno/{b['id_turno']}", headers=b["headers"]).json()
    id_mov_b = movs_b[0]["id_movimiento"]

    client.delete(f"/borrar_movimiento/{id_mov_b}", headers=a["headers"])

    movs_b_despues = client.get(f"/movimientos_turno/{b['id_turno']}", headers=b["headers"]).json()
    ids_restantes = {m["id_movimiento"] for m in movs_b_despues}
    assert id_mov_b in ids_restantes, "¡Tienda A pudo cancelar un movimiento de Tienda B!"


def test_clientes_fiado_no_se_mezclan(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]

    client.post("/clientes", headers=b["headers"], json={"nombre": "Cliente secreto de B", "telefono": "5511112222"})

    clientes_a = client.get("/clientes", headers=a["headers"]).json()
    nombres_a = {c["nombre"] for c in clientes_a}
    assert "Cliente secreto de B" not in nombres_a, "¡Tienda A ve un cliente fiado de Tienda B!"


def test_no_se_puede_borrar_cliente_de_otra_tienda(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]

    resp = client.post("/clientes", headers=b["headers"], json={"nombre": "No debe borrarse", "telefono": None})
    id_cliente_b = resp.json()["id_cliente"]

    client.delete(f"/clientes/{id_cliente_b}", headers=a["headers"])

    clientes_b = client.get("/clientes", headers=b["headers"]).json()
    ids_b = {c["id_cliente"] for c in clientes_b}
    assert id_cliente_b in ids_b, "¡Tienda A pudo borrar un cliente de Tienda B!"


def test_historial_turnos_no_se_mezcla(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]

    # Cerramos el turno de B para que aparezca en su historial
    client.post(f"/corte_caja/{b['id_turno']}", headers=b["headers"])

    historial_a = client.get("/historial_turnos", headers=a["headers"]).json()
    ids_a = {t["id_turno"] for t in historial_a}
    assert b["id_turno"] not in ids_a, "¡El historial de Tienda A incluye un turno de Tienda B!"
