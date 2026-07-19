"""
Fixtures compartidas para el test suite de aislamiento multi-tenant (#12 del roadmap).

CÓMO FUNCIONA:
1. Clona la ESTRUCTURA de tablas (sin datos) desde tu base local ya restaurada
   (la que usaste para la prueba de restore del #10) hacia un schema nuevo y
   vacío llamado `caja_rapida_test`.
2. Siembra 2 "tiendas" de prueba directamente por SQL (igual que en producción,
   donde el alta de tienda nueva también es manual — ver docs/docsalta-cliente-nuevo.md).
3. Para todo lo demás (productos, turnos, movimientos, clientes) usa la API real
   vía TestClient, para no tener que adivinar columnas — así los datos de prueba
   se crean exactamente como los crearía un cajero real.
4. Al terminar la sesión de tests, borra el schema de prueba (a menos que
   pongas KEEP_TEST_DB=1 en el entorno, útil para depurar a mano en Workbench).

NO TOCA tu base real ni la de Aiven: todo corre contra un schema nuevo en tu
MySQL local.
"""
import os
import sys
from pathlib import Path
import pytest
from dotenv import load_dotenv

# ─── Aseguramos que la raíz del proyecto sea importable ───────────────────────
# (pytest, al correr desde tests/, no agrega automáticamente la carpeta padre
# a sys.path — sin esto, "from main import app" tronaría con ModuleNotFoundError)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ─── Config de la base de prueba (se resuelve ANTES de importar la app) ───────
load_dotenv()

SOURCE_SCHEMA = os.getenv("TEST_SOURCE_SCHEMA", "defaultdb")
TEST_SCHEMA = os.getenv("TEST_DB_NAME", "caja_rapida_test")

# Sobreescribe DB_NAME para que database.py arme su pool apuntando al schema
# de prueba. Las demás variables (host/user/password) se reusan de tu .env,
# porque es el mismo servidor MySQL local, solo cambia el schema.
os.environ["DB_NAME"] = TEST_SCHEMA
os.environ.setdefault("ENV", "development")
os.environ.setdefault("SECRET_KEY", os.getenv("SECRET_KEY") or "clave-solo-para-tests-no-usar-en-produccion")


def _conexion_admin():
    """Conexión SIN schema fija, para crear/borrar el schema de prueba."""
    import mysql.connector
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


@pytest.fixture(scope="session")
def _test_schema_listo():
    """Crea `caja_rapida_test` clonando la estructura de tablas de SOURCE_SCHEMA,
    y lo destruye al final de toda la sesión de tests."""
    conn = _conexion_admin()
    cur = conn.cursor()
    try:
        cur.execute(f"SHOW DATABASES LIKE '{SOURCE_SCHEMA}'")
        if not cur.fetchone():
            raise RuntimeError(
                f"No encontré el schema de origen '{SOURCE_SCHEMA}' en tu MySQL local.\n"
                f"Si tu base local restaurada tiene otro nombre, ponlo en tu .env como:\n"
                f"TEST_SOURCE_SCHEMA=nombre_real_de_tu_schema"
            )
        cur.execute(f"DROP DATABASE IF EXISTS `{TEST_SCHEMA}`")
        cur.execute(f"CREATE DATABASE `{TEST_SCHEMA}`")
        # OJO: usamos SHOW FULL TABLES + filtro 'BASE TABLE' a propósito, no
        # SHOW TABLES a secas — así ignoramos VIEWS (como v_alertas), que no
        # se pueden clonar con CREATE TABLE ... LIKE.
        cur.execute(f"SHOW FULL TABLES FROM `{SOURCE_SCHEMA}` WHERE Table_type = 'BASE TABLE'")
        tablas = [r[0] for r in cur.fetchall()]
        if not tablas:
            raise RuntimeError(f"El schema '{SOURCE_SCHEMA}' no tiene tablas.")
        for tabla in tablas:
            cur.execute(f"CREATE TABLE `{TEST_SCHEMA}`.`{tabla}` LIKE `{SOURCE_SCHEMA}`.`{tabla}`")
        conn.commit()
    finally:
        cur.close()
        conn.close()

    yield

    if os.getenv("KEEP_TEST_DB") != "1":
        conn = _conexion_admin()
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS `{TEST_SCHEMA}`")
        conn.commit()
        cur.close()
        conn.close()


@pytest.fixture(scope="session")
def app(_test_schema_listo):
    """Importa la app YA con DB_NAME apuntando al schema de prueba (import tardío
    a propósito: database.py arma su connection pool en cuanto se importa)."""
    from main import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope="session")
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


def _crear_tienda(nombre: str) -> int:
    """Alta directa por SQL — así se hace hoy en producción también (#8)."""
    from database import conectar_bd
    conexion = conectar_bd()
    cursor = conexion.cursor()
    try:
        cursor.execute("INSERT INTO tiendas (nombre_comercial, activa) VALUES (%s, 1)", (nombre,))
        conexion.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conexion.close()


def _crear_cajero(id_tienda: int, username: str) -> dict:
    """Crea un usuario cajero directo por SQL (mismo INSERT mínimo que usa
    admin_crear_usuario) y arma su JWT a mano, sin pasar por /login — no
    necesitamos probar el login aquí, solo aislamiento entre tiendas."""
    from database import conectar_bd
    from auth import SECRET_KEY, ALGORITHM
    from jose import jwt
    from datetime import datetime, timedelta, timezone

    conexion = conectar_bd()
    cursor = conexion.cursor(dictionary=True)
    try:
        cursor.execute(
            "INSERT INTO usuarios (id_tienda, username, password_hash, rol) VALUES (%s, %s, %s, 'cajero')",
            (id_tienda, username, "$2b$12$hashfalsoparatest0000000000000000000000000000000000")
        )
        conexion.commit()
        id_usuario = cursor.lastrowid

        # Leemos el token_version REAL que quedó en la fila (no asumimos su default)
        cursor.execute("SELECT token_version FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        token_version = cursor.fetchone()["token_version"]
    finally:
        cursor.close()
        conexion.close()

    token = jwt.encode(
        {
            "id_tienda": id_tienda,
            "id_usuario": id_usuario,
            "rol": "cajero",
            "token_version": token_version,
            "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
        },
        SECRET_KEY, algorithm=ALGORITHM,
    )
    return {"id_usuario": id_usuario, "id_tienda": id_tienda, "token": token,
            "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture(scope="function")
def dos_tiendas(client, _test_schema_listo):
    """Crea 2 tiendas independientes, cada una con su propio cajero, y abre
    turno en ambas usando la API real. Se recrea en cada test (function-scope)
    para que ningún test contamine el estado de otro."""
    tienda_a = _crear_tienda("Tienda de prueba A")
    tienda_b = _crear_tienda("Tienda de prueba B")

    cajero_a = _crear_cajero(tienda_a, f"cajero_a_{tienda_a}")
    cajero_b = _crear_cajero(tienda_b, f"cajero_b_{tienda_b}")

    turno_a = client.post("/abrir_turno", headers=cajero_a["headers"]).json()["id_turno"]
    turno_b = client.post("/abrir_turno", headers=cajero_b["headers"]).json()["id_turno"]

    cajero_a["id_turno"] = turno_a
    cajero_b["id_turno"] = turno_b

    return {"a": cajero_a, "b": cajero_b}