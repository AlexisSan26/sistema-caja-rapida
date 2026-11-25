"""
Tests de /admin/*: solo el superadmin entra (#13), alta de tiendas y usuarios,
revocación de sesiones al resetear contraseña, eliminar o editar un usuario
(#4 y #62), suscripción/impago (#7) y desactivar/activar tienda.

Usa las fixtures `tienda_nueva` y `crear_usuario` (se agregan en conftest.py).
"""
import pytest


@pytest.fixture
def superadmin(client, tienda_nueva, crear_usuario):
    return crear_usuario(tienda_nueva, rol="superadmin")


def _sql_uno(consulta, params=()):
    from database import conectar_bd
    conexion = conectar_bd()
    cursor = conexion.cursor()
    try:
        cursor.execute(consulta, params)
        return cursor.fetchone()
    finally:
        cursor.close()
        conexion.close()


# Todos los endpoints /admin/*, con un cuerpo válido (si no, FastAPI respondería
# 422 antes de llegar a la revisión de rol y el test no probaría lo que debe).
ENDPOINTS_ADMIN = [
    ("GET", "/admin/tiendas", None),
    ("POST", "/admin/tiendas", {"nombre_comercial": "X"}),
    ("PUT", "/admin/tiendas/1/activar", None),
    ("PUT", "/admin/tiendas/1/desactivar", None),
    ("PUT", "/admin/tiendas/1/editar", {"nombre_comercial": "X"}),
    ("GET", "/admin/usuarios", None),
    ("POST", "/admin/usuarios", {"username": "x", "password": "123456", "id_tienda": 1, "rol": "cajero"}),
    ("PUT", "/admin/usuarios/1/reset_password", {"nuevo_password": "123456"}),
    ("DELETE", "/admin/usuarios/1", None),
    ("PUT", "/admin/usuarios/1/editar", {"id_tienda": 1, "rol": "cajero"}),
    ("GET", "/admin/ventas_hoy", None),
    ("GET", "/admin/ventas_reporte?fecha_inicio=2020-01-01&fecha_fin=2030-01-01", None),
    ("GET", "/admin/tiendas/1/suscripcion", None),
    ("PUT", "/admin/tiendas/1/suscripcion", {"dia_corte": 1, "monto_mensual": 0, "estado_pago": "AL_DIA"}),
    ("GET", "/admin/tienda/1/inventario", None),
    ("GET", "/admin/log_auditoria/1", None),
]


# ─── Acceso ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("metodo,ruta,cuerpo", ENDPOINTS_ADMIN)
def test_un_cajero_no_entra_a_ningun_endpoint_admin(client, dos_tiendas, metodo, ruta, cuerpo):
    a = dos_tiendas["a"]
    r = client.request(metodo, ruta, headers=a["headers"], json=cuerpo)
    assert r.status_code == 403, f"{metodo} {ruta} respondió {r.status_code}"


def test_sin_token_no_entra_a_admin(client):
    assert client.get("/admin/tiendas").status_code == 401


# ─── Alta de tiendas y usuarios ───────────────────────────────────────────────
def test_superadmin_crea_tienda_y_usuario_que_puede_entrar(client, superadmin):
    h = superadmin["headers"]
    r = client.post("/admin/tiendas", headers=h, json={"nombre_comercial": "Tienda nueva test"})
    assert r.status_code == 200, r.text
    id_tienda = r.json()["id_tienda"]

    r = client.post("/admin/usuarios", headers=h, json={
        "username": f"nuevo_{id_tienda}", "password": "clave-123456", "id_tienda": id_tienda, "rol": "cajero"})
    assert r.status_code == 200, r.text

    login = client.post("/login", json={"username": f"nuevo_{id_tienda}", "password": "clave-123456"})
    assert login.status_code == 200, login.text


def test_alta_con_datos_invalidos(client, superadmin):
    h = superadmin["headers"]
    assert client.post("/admin/tiendas", headers=h, json={"nombre_comercial": "   "}).status_code == 400
    r = client.post("/admin/usuarios", headers=h, json={
        "username": "x_rol", "password": "123456", "id_tienda": superadmin["id_tienda"], "rol": "dueño"})
    assert r.status_code == 422  # el rol «dueño» todavía no existe (#28)


def test_username_duplicado_da_409(client, superadmin):
    h = superadmin["headers"]
    cuerpo = {"username": f"dup_{superadmin['id_tienda']}", "password": "123456",
              "id_tienda": superadmin["id_tienda"], "rol": "cajero"}
    assert client.post("/admin/usuarios", headers=h, json=cuerpo).status_code == 200
    assert client.post("/admin/usuarios", headers=h, json=cuerpo).status_code == 409


# ─── Revocar sesiones (#4 y #62) ──────────────────────────────────────────────
def test_resetear_password_invalida_la_sesion_del_usuario(client, superadmin, tienda_nueva, crear_usuario):
    cajero = crear_usuario(tienda_nueva)
    assert client.get("/yo", headers=cajero["headers"]).status_code == 200  # sesión activa

    r = client.put(f"/admin/usuarios/{cajero['id_usuario']}/reset_password",
                   headers=superadmin["headers"], json={"nuevo_password": "clave-reseteada-1"})
    assert r.status_code == 200, r.text

    assert client.get("/yo", headers=cajero["headers"]).status_code == 401
    assert client.post("/login", json={"username": cajero["username"],
                                       "password": "clave-reseteada-1"}).status_code == 200


def test_eliminar_usuario_invalida_su_sesion(client, superadmin, tienda_nueva, crear_usuario):
    cajero = crear_usuario(tienda_nueva)
    assert client.get("/yo", headers=cajero["headers"]).status_code == 200

    r = client.delete(f"/admin/usuarios/{cajero['id_usuario']}", headers=superadmin["headers"])
    assert r.status_code == 200, r.text
    assert client.get("/yo", headers=cajero["headers"]).status_code == 401


def test_superadmin_no_puede_eliminarse_a_si_mismo(client, superadmin):
    r = client.delete(f"/admin/usuarios/{superadmin['id_usuario']}", headers=superadmin["headers"])
    assert r.status_code == 400


def test_editar_usuario_invalida_su_sesion(client, superadmin, tienda_nueva, crear_usuario):
    cajero = crear_usuario(tienda_nueva)
    assert client.get("/yo", headers=cajero["headers"]).status_code == 200

    r = client.put(f"/admin/usuarios/{cajero['id_usuario']}/editar", headers=superadmin["headers"],
                   json={"id_tienda": tienda_nueva, "rol": "superadmin"})
    assert r.status_code == 200, r.text
    assert client.get("/yo", headers=cajero["headers"]).status_code == 401


def test_editar_usuario_a_tienda_inexistente_da_404(client, superadmin, tienda_nueva, crear_usuario):
    cajero = crear_usuario(tienda_nueva)
    r = client.put(f"/admin/usuarios/{cajero['id_usuario']}/editar", headers=superadmin["headers"],
                   json={"id_tienda": 99999999, "rol": "cajero"})
    assert r.status_code == 404


# ─── Suscripción / impago (#7) ────────────────────────────────────────────────
def test_marcar_tienda_atrasada_bloquea_y_al_dia_desbloquea(client, superadmin, tienda_nueva, crear_usuario):
    cajero = crear_usuario(tienda_nueva)
    assert client.get("/yo", headers=cajero["headers"]).status_code == 200

    def suscripcion(estado):
        return client.put(f"/admin/tiendas/{tienda_nueva}/suscripcion", headers=superadmin["headers"],
                          json={"dia_corte": 5, "monto_mensual": 199, "estado_pago": estado})

    assert suscripcion("ATRASADO").status_code == 200
    assert client.get("/yo", headers=cajero["headers"]).status_code == 402
    assert suscripcion("AL_DIA").status_code == 200
    assert client.get("/yo", headers=cajero["headers"]).status_code == 200


def test_suscripcion_valida_los_datos(client, superadmin, tienda_nueva):
    def suscripcion(**kw):
        cuerpo = {"dia_corte": 5, "monto_mensual": 199, "estado_pago": "AL_DIA", **kw}
        return client.put(f"/admin/tiendas/{tienda_nueva}/suscripcion",
                          headers=superadmin["headers"], json=cuerpo)

    assert suscripcion(estado_pago="PAGADO").status_code == 422
    assert suscripcion(dia_corte=0).status_code == 400
    assert suscripcion(dia_corte=32).status_code == 400
    assert suscripcion(monto_mensual=-1).status_code == 400


# ─── Desactivar / activar tienda ──────────────────────────────────────────────
def test_desactivar_tienda_bloquea_y_cierra_turno_activar_la_reabre(client, superadmin, dos_tiendas):
    a = dos_tiendas["a"]
    assert client.get("/yo", headers=a["headers"]).status_code == 200
    h = superadmin["headers"]

    assert client.put(f"/admin/tiendas/{a['id_tienda']}/desactivar", headers=h).status_code == 200
    assert client.get("/yo", headers=a["headers"]).status_code == 401
    estado = _sql_uno("SELECT estado FROM turnos WHERE id_turno = %s", (a["id_turno"],))[0]
    assert estado == "CERRADO"

    assert client.put(f"/admin/tiendas/{a['id_tienda']}/activar", headers=h).status_code == 200
    assert client.get("/yo", headers=a["headers"]).status_code == 200


def test_despues_de_reactivar_la_tienda_se_puede_abrir_turno(client, superadmin, dos_tiendas):
    a = dos_tiendas["a"]
    h = superadmin["headers"]
    client.put(f"/admin/tiendas/{a['id_tienda']}/desactivar", headers=h)
    client.put(f"/admin/tiendas/{a['id_tienda']}/activar", headers=h)

    r = client.post("/abrir_turno", headers=a["headers"])
    assert r.status_code == 200, r.text
    nuevo = r.json()["id_turno"]
    assert nuevo is not None and nuevo != a["id_turno"]


def test_password_corta_y_estado_pago_invalido_se_rechazan(client, superadmin):
    h = superadmin["headers"]
    r = client.post("/admin/usuarios", headers=h, json={
        "username": "corta_68", "password": "12345", "id_tienda": superadmin["id_tienda"], "rol": "cajero"})
    assert r.status_code == 400
    r = client.put("/admin/usuarios/1/reset_password", headers=h, json={"nuevo_password": "12345"})
    assert r.status_code == 400
    r = client.put(f"/admin/tiendas/{superadmin['id_tienda']}/suscripcion", headers=h,
                   json={"dia_corte": 5, "monto_mensual": 0, "estado_pago": "VENCIDO"})
    assert r.status_code == 422



def test_superadmin_no_puede_degradarse_a_si_mismo(client, superadmin):
    r = client.put(f"/admin/usuarios/{superadmin['id_usuario']}/editar", headers=superadmin["headers"],
                   json={"id_tienda": superadmin["id_tienda"], "rol": "cajero"})
    assert r.status_code == 400


def test_crear_usuario_en_tienda_inexistente_da_404(client, superadmin):
    r = client.post("/admin/usuarios", headers=superadmin["headers"],
                    json={"username": "sin_tienda_96", "password": "123456",
                          "id_tienda": 99999999, "rol": "cajero"})
    assert r.status_code == 404