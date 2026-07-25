import json
from fastapi import APIRouter, Depends
from database import conectar_bd
from auth import get_current_user
from models import TokenData, ConfiguracionTicket, GastoFijo

router = APIRouter()


@router.get("/configuracion_tienda")
def obtener_configuracion(user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT config_resumen FROM tiendas WHERE id_tienda = %s", (user.id_tienda,))
        row = cursor.fetchone()
        data = json.loads(row['config_resumen']) if row and row['config_resumen'] else []
        if isinstance(data, list):
            reglas, gastos_fijos = data, []
        else:
            reglas = data.get('reglas', [])
            gastos_fijos = data.get('gastos_fijos', [])
        return {"reglas": reglas, "gastos_fijos": gastos_fijos}
    finally:
        if cursor:
            cursor.close()
        conexion.close()


@router.put("/configuracion_tienda")
def actualizar_configuracion(config: ConfiguracionTicket, user: TokenData = Depends(get_current_user)):
    conexion = conectar_bd()
    cursor = None
    try:
        cursor = conexion.cursor()
        json_str = json.dumps({
            "reglas": [r.model_dump() for r in config.reglas],
            "gastos_fijos": [g.model_dump() for g in config.gastos_fijos],
        })
        cursor.execute("UPDATE tiendas SET config_resumen = %s WHERE id_tienda = %s", (json_str, user.id_tienda))
        conexion.commit()
        return {"mensaje": "Configuración del ticket actualizada correctamente"}
    finally:
        if cursor:
            cursor.close()
        conexion.close()