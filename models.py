from typing import List, Literal
from pydantic import BaseModel, Field
from enum import Enum


# ─── Modelos de Auth ──────────────────────────────────────────────────────────
class TokenData(BaseModel):
    id_tienda: int
    id_usuario: int
    rol: str = "cajero"


class LoginRequest(BaseModel):
    username: str
    password: str


# ─── Modelos Operativos ───────────────────────────────────────────────────────
class TiposPermitidos(str, Enum):
    VENTA = "VENTA"
    RETIRO = "RETIRO"
    FONDO_CAJA = "FONDO_CAJA"
    COBRO_FIADO = "COBRO_FIADO"


class Movimiento(BaseModel):
    id_turno: int
    tipo_movimiento: TiposPermitidos
    producto: str = "Venta general"
    cantidad: float = Field(default=1.0, gt=0)
    precio_unitario: float = Field(gt=0)


class ActualizacionPrecio(BaseModel):
    nombre_producto: str
    nuevo_precio: float


class ProductoNuevo(BaseModel):
    codigo_barras: str | None = None
    nombre_producto: str
    precio_sugerido: float
    stock_actual: float = 0
    stock_minimo: float = 5
    proveedor: str | None = None
    fecha_caducidad: str | None = None
    unidad_medida: str = "pieza"


class ActualizacionProducto(BaseModel):
    nombre_producto: str
    precio_sugerido: float
    stock_actual: float
    stock_minimo: float
    proveedor: str | None = None
    codigo_barras: str | None = None
    fecha_caducidad: str | None = None
    unidad_medida: str = "pieza"


class EntradaMercancia(BaseModel):
    id_producto: int
    cantidad: float
    fecha_caducidad: str | None = None
    notas: str | None = None


class ResurtidoPorCodigo(BaseModel):
    codigo_barras: str
    cantidad: float
    fecha_caducidad: str | None = None


class ItemEntradaLote(BaseModel):
    id_producto: int
    cantidad: float
    fecha_caducidad: str | None = None


class EntradaLote(BaseModel):
    items: list[ItemEntradaLote]
    nota_general: str | None = None


class ClienteNuevo(BaseModel):
    nombre: str
    telefono: str | None = None


class ItemFiado(BaseModel):
    id_cuenta: int
    id_turno: int
    producto: str
    cantidad: float = 1.0
    precio: float


class AbonoFiado(BaseModel):
    id_cuenta: int
    id_turno: int
    monto: float = Field(gt=0)
    nota: str | None = None


class ItemVenta(BaseModel):
    producto: str
    cantidad: float = 1.0
    precio_unitario: float


class VentaLote(BaseModel):
    id_turno: int
    items: list[ItemVenta]


# ─── NUEVO MODELO: Merma (Prioridad 2B) ───────────────────────────────────────
class MermaProducto(BaseModel):
    id_producto: int
    cantidad: float = Field(gt=0)
    motivo: Literal["merma", "caducado", "uso_personal", "daño"] = "merma"
    nota: str | None = None


# ─── Modelos Admin ────────────────────────────────────────────────────────────
class ReglaResumen(BaseModel):
    nombre: str
    claves: str
    ids_productos: List[int] = []


class ConfiguracionTicket(BaseModel):
    reglas: List[ReglaResumen] = []


class TiendaNueva(BaseModel):
    nombre_comercial: str


class UsuarioNuevo(BaseModel):
    username: str
    password: str
    id_tienda: int
    rol: str = "cajero"


class ResetPassword(BaseModel):
    nuevo_password: str


class ActualizacionNombreTienda(BaseModel):
    nombre_comercial: str


class ActualizacionUsuario(BaseModel):
    id_tienda: int
    rol: str


class SuscripcionTienda(BaseModel):
    dia_corte: int
    monto_mensual: float
    estado_pago: str