import os
import mysql.connector
import mysql.connector.pooling
from dotenv import load_dotenv

load_dotenv()

db_config = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 28257)),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'ssl_disabled': False,
    'time_zone': '-06:00',
}

# ─── RENDIMIENTO: Pool de conexiones a 8 ──────────────────────────────────────
db_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="cajapool_saas",
    pool_size=8,
    pool_reset_session=True,
    connection_timeout=10,
    **db_config
)


# ─── Helpers ──────────────────────────────────────────────────────────────────
def conectar_bd():
    return db_pool.get_connection()