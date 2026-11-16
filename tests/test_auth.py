"""
Tests de autenticación: login, tokens, cambio de contraseña propio (#95),
sesión invalidada (#4), tienda atrasada (#7), tienda/usuario inactivo y que el
rol salga de la base de datos y no del token.

Usa las fixtures `tienda_nueva` y `crear_usuario` (se agregan en conftest.py).
"""
from datetime import datetime, timedelta, timezone

from jose import jwt


def _sql(consulta, params=()):
    """Ejecuta un UPDATE directo en la base de prueba (para simular estados)."""
    from database import conectar_bd
    conexion = conectar_bd()
    cursor = conexion.cursor()
    try:
        cursor.execute(consulta, params)
        conexion.commit()
    finally:
        cursor.close()
        conexion.close()


def _login(client, username, password):
    return client.post("/login", json={"username": username, "password": password})


# ─── Login ────────────────────────────────────────────────────────────────────
def test_login_correcto_devuelve_token_que_funciona(client, tienda_nueva, crear_usuario):
    u = crear_usuario(tienda_nueva)
    r = _login(client, u["username"], u["password"])
    assert r.status_code == 200, r.text
    assert r.json()["rol"] == "cajero"

    yo = client.get("/yo", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert yo.status_code == 200
    assert yo.json()["username"] == u["username"]


def test_login_con_password_mala_o_usuario_inexistente_da_el_mismo_401(client, tienda_nueva, crear_usuario):
    u = crear_usuario(tienda_nueva)
    mala = _login(client, u["username"], "contraseña-incorrecta")
    inexistente = _login(client, "usuario_que_no_existe_xyz", "lo-que-sea")
    assert mala.status_code == inexistente.status_code == 401
    assert mala.json() == inexistente.json()  # no revela si el usuario existe (#63)


# ─── Tokens ───────────────────────────────────────────────────────────────────
def test_sin_token_o_con_token_basura_da_401(client):
    assert client.get("/yo").status_code == 401
    assert client.get("/yo", headers={"Authorization": "Bearer basura"}).status_code == 401


def test_token_firmado_con_otra_clave_da_401(client, tienda_nueva, crear_usuario):
    u = crear_usuario(tienda_nueva)
    falso = jwt.encode(
        {"id_tienda": u["id_tienda"], "id_usuario": u["id_usuario"], "rol": "cajero",
         "token_version": 0, "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1)},
        "otra-clave-que-no-es-la-del-servidor", algorithm="HS256",
    )
    assert client.get("/yo", headers={"Authorization": f"Bearer {falso}"}).status_code == 401


def test_el_rol_sale_de_la_base_de_datos_no_del_token(client, tienda_nueva, crear_usuario):
    from auth import SECRET_KEY, ALGORITHM
    u = crear_usuario(tienda_nueva)  # cajero en la BD
    version = jwt.get_unverified_claims(u["token"])["token_version"]
    token = jwt.encode(
        {"id_tienda": u["id_tienda"], "id_usuario": u["id_usuario"], "rol": "superadmin",
         "token_version": version, "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1)},
        SECRET_KEY, algorithm=ALGORITHM,
    )
    r = client.get("/admin/tiendas", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


# ─── Cambio de contraseña propio (#95) ────────────────────────────────────────
def test_cambiar_password_invalida_el_token_viejo(client, tienda_nueva, crear_usuario):
    u = crear_usuario(tienda_nueva)
    r = client.put("/yo/password", headers=u["headers"], json={
        "password_actual": u["password"], "password_nueva": "clave-nueva-123"})
    assert r.status_code == 200, r.text
    token_nuevo = r.json()["access_token"]

    assert client.get("/yo", headers=u["headers"]).status_code == 401  # token viejo ya no sirve
    assert client.get("/yo", headers={"Authorization": f"Bearer {token_nuevo}"}).status_code == 200
    assert _login(client, u["username"], "clave-nueva-123").status_code == 200
    assert _login(client, u["username"], u["password"]).status_code == 401


def test_cambiar_password_valida_los_datos(client, tienda_nueva, crear_usuario):
    u = crear_usuario(tienda_nueva)
    actual = u["password"]

    r = client.put("/yo/password", headers=u["headers"],
                   json={"password_actual": "no-es-la-actual", "password_nueva": "clave-nueva-123"})
    assert r.status_code == 400
    r = client.put("/yo/password", headers=u["headers"],
                   json={"password_actual": actual, "password_nueva": actual})
    assert r.status_code == 400
    r = client.put("/yo/password", headers=u["headers"],
                   json={"password_actual": actual, "password_nueva": "123"})
    assert r.status_code == 422  # menos de 6 caracteres


# ─── Estados de tienda y usuario ──────────────────────────────────────────────
def test_tienda_atrasada_recibe_402(client, tienda_nueva, crear_usuario):
    u = crear_usuario(tienda_nueva)
    _sql("UPDATE tiendas SET estado_pago = 'ATRASADO' WHERE id_tienda = %s", (tienda_nueva,))
    r = client.get("/yo", headers=u["headers"])
    assert r.status_code == 402


def test_superadmin_no_se_bloquea_por_tienda_atrasada(client, tienda_nueva, crear_usuario):
    sa = crear_usuario(tienda_nueva, rol="superadmin")
    _sql("UPDATE tiendas SET estado_pago = 'ATRASADO' WHERE id_tienda = %s", (tienda_nueva,))
    assert client.get("/yo", headers=sa["headers"]).status_code == 200


def test_tienda_desactivada_da_401(client, tienda_nueva, crear_usuario):
    u = crear_usuario(tienda_nueva)
    _sql("UPDATE tiendas SET activa = 0 WHERE id_tienda = %s", (tienda_nueva,))
    assert client.get("/yo", headers=u["headers"]).status_code == 401


def test_usuario_inactivo_da_401(client, tienda_nueva, crear_usuario):
    u = crear_usuario(tienda_nueva)
    _sql("UPDATE usuarios SET activo = 0 WHERE id_usuario = %s", (u["id_usuario"],))
    assert client.get("/yo", headers=u["headers"]).status_code == 401