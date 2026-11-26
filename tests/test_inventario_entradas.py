"""
Tests de entradas de mercancía (#61), inventario, mermas, alertas y del candado
de nombres duplicados sin código de barras (#89).
"""
import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _crear(client, caja, nombre, codigo=None, stock=10, minimo=0, precio=10):
    return client.post("/registrar_producto", headers=caja["headers"], json={
        "codigo_barras": codigo, "nombre_producto": nombre, "precio_sugerido": precio,
        "stock_actual": stock, "stock_minimo": minimo,
    })


def _producto(client, caja, nombre, codigo, stock=10, minimo=0):
    r = _crear(client, caja, nombre, codigo, stock, minimo)
    assert r.status_code == 200, r.text
    return r.json()["id_producto"]


def _fila(client, caja, id_producto):
    for p in client.get("/inventario", headers=caja["headers"]).json():
        if p["id_producto"] == id_producto:
            return p
    return None


def _stock(client, caja, id_producto):
    fila = _fila(client, caja, id_producto)
    return float(fila["stock_actual"]) if fila else None


def _entrada(client, caja, items):
    return client.post("/entrada_mercancia_lote", headers=caja["headers"],
                       json={"items": items, "nota_general": "test"})


def _editar(client, caja, id_producto, nombre, precio=10, codigo=None):
    return client.put(f"/actualizar_producto/{id_producto}", headers=caja["headers"], json={
        "nombre_producto": nombre, "precio_sugerido": precio, "precio_costo": None,
        "stock_actual": 10, "stock_minimo": 0, "proveedor": None,
        "codigo_barras": codigo, "fecha_caducidad": None, "unidad_medida": "pieza",
    })


# ─── Entradas de mercancía ────────────────────────────────────────────────────
def test_entrada_suma_stock_actualiza_costo_y_queda_en_historial(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Producto entrada", "7500000003001", stock=5)

    r = _entrada(client, a, [{"id_producto": pid, "cantidad": 10, "precio_costo": 4}])
    assert r.status_code == 200, r.text
    assert _stock(client, a, pid) == pytest.approx(15)
    assert float(_fila(client, a, pid)["precio_costo"]) == pytest.approx(4)

    historial = client.get("/historial_entradas", headers=a["headers"]).json()
    assert [h["nombre_producto"] for h in historial] == ["Producto entrada"]


def test_entrada_con_producto_de_otra_tienda_se_rechaza(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    pid_b = _producto(client, b, "Producto de B", "7500000003002", stock=10)

    r = _entrada(client, a, [{"id_producto": pid_b, "cantidad": 99}])
    assert r.status_code == 400
    assert _stock(client, b, pid_b) == pytest.approx(10)
    assert client.get("/historial_entradas", headers=b["headers"]).json() == []
    assert client.get("/historial_entradas", headers=a["headers"]).json() == []


def test_lote_con_un_producto_ajeno_se_rechaza_completo(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    propio = _producto(client, a, "Producto propio", "7500000003003", stock=10)
    ajeno = _producto(client, b, "Producto ajeno", "7500000003004", stock=10)

    r = _entrada(client, a, [{"id_producto": propio, "cantidad": 5},
                             {"id_producto": ajeno, "cantidad": 5}])
    assert r.status_code == 400
    assert _stock(client, a, propio) == pytest.approx(10)  # ni siquiera el propio se aplicó


def test_historial_de_entradas_no_mezcla_tiendas(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    pa = _producto(client, a, "Solo de A", "7500000003005")
    pb = _producto(client, b, "Solo de B", "7500000003006")
    _entrada(client, a, [{"id_producto": pa, "cantidad": 1}])
    _entrada(client, b, [{"id_producto": pb, "cantidad": 1}])

    nombres_a = [h["nombre_producto"] for h in client.get("/historial_entradas", headers=a["headers"]).json()]
    nombres_b = [h["nombre_producto"] for h in client.get("/historial_entradas", headers=b["headers"]).json()]
    assert nombres_a == ["Solo de A"]
    assert nombres_b == ["Solo de B"]


# ─── Mermas, alertas y archivado ──────────────────────────────────────────────
def test_merma_resta_stock(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Producto merma", "7500000003007", stock=10)
    r = client.post("/registrar_merma", headers=a["headers"],
                    json={"id_producto": pid, "cantidad": 2, "motivo": "merma"})
    assert r.status_code == 200, r.text
    assert _stock(client, a, pid) == pytest.approx(8)


def test_merma_de_producto_ajeno_da_404(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    pid_b = _producto(client, b, "Producto de B", "7500000003008", stock=10)
    r = client.post("/registrar_merma", headers=a["headers"],
                    json={"id_producto": pid_b, "cantidad": 2, "motivo": "merma"})
    assert r.status_code == 404
    assert _stock(client, b, pid_b) == pytest.approx(10)


def test_alertas_solo_incluye_stock_bajo(client, dos_tiendas):
    a = dos_tiendas["a"]
    bajo = _producto(client, a, "Producto bajo", "7500000003009", stock=2, minimo=5)
    ok = _producto(client, a, "Producto sano", "7500000003010", stock=50, minimo=5)
    ids = {x["id_producto"] for x in client.get("/alertas", headers=a["headers"]).json()}
    assert bajo in ids
    assert ok not in ids


def test_eliminar_producto_lo_archiva(client, dos_tiendas):
    a = dos_tiendas["a"]
    pid = _producto(client, a, "Producto a archivar", "7500000003011")
    assert client.delete(f"/eliminar_producto/{pid}", headers=a["headers"]).status_code == 200
    assert _fila(client, a, pid) is None


# ─── #89: candado de nombres repetidos sin código de barras ───────────────────
def test_nombre_repetido_sin_codigo_se_rechaza(client, dos_tiendas):
    a = dos_tiendas["a"]
    assert _crear(client, a, "Plantillas dup").status_code == 200
    r = _crear(client, a, "plantillas DUP")  # mismo nombre, otra capitalización
    assert r.status_code == 409
    assert "Ya existe" in r.json()["detail"]


def test_nombre_repetido_con_codigo_si_se_permite(client, dos_tiendas):
    a = dos_tiendas["a"]
    assert _crear(client, a, "Producto igual", "7500000004001").status_code == 200
    assert _crear(client, a, "Producto igual", "7500000004002").status_code == 200


def test_mismo_nombre_en_otra_tienda_si_se_permite(client, dos_tiendas):
    a, b = dos_tiendas["a"], dos_tiendas["b"]
    assert _crear(client, a, "Nombre compartido").status_code == 200
    assert _crear(client, b, "Nombre compartido").status_code == 200


def test_renombrar_a_un_nombre_existente_sin_codigo_se_rechaza(client, dos_tiendas):
    a = dos_tiendas["a"]
    _crear(client, a, "Nombre uno")
    id_dos = _crear(client, a, "Nombre dos").json()["id_producto"]
    r = _editar(client, a, id_dos, "NOMBRE UNO")
    assert r.status_code == 409


def test_editar_precio_sin_cambiar_nombre_no_estorba(client, dos_tiendas):
    a = dos_tiendas["a"]
    # Duplicado "heredado": el mismo nombre con y sin código
    id_sin_codigo = _crear(client, a, "Heredado").json()["id_producto"]
    assert _crear(client, a, "Heredado", "7500000004003").status_code == 200

    r = _editar(client, a, id_sin_codigo, "Heredado", precio=22)
    assert r.status_code == 200, r.text
    assert float(_fila(client, a, id_sin_codigo)["precio_sugerido"]) == pytest.approx(22)



def test_historial_de_entradas_trae_la_unidad_y_la_merma_en_negativo(client, dos_tiendas):
    """#102: la pantalla necesita la unidad real y el signo de la merma."""
    a = dos_tiendas["a"]
    r = client.post("/registrar_producto", headers=a["headers"], json={
        "codigo_barras": "7500000000102", "nombre_producto": "Frijol a granel",
        "precio_sugerido": 40, "stock_actual": 10, "unidad_medida": "kg"})
    assert r.status_code == 200, r.text
    pid = r.json()["id_producto"]
    r = client.post("/registrar_merma", headers=a["headers"], json={"id_producto": pid, "cantidad": 2})
    assert r.status_code == 200, r.text

    fila = client.get("/historial_entradas", headers=a["headers"]).json()[0]
    assert fila["unidad_medida"] == "kg"
    assert float(fila["cantidad"]) == -2