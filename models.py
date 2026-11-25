from typing import List, Literal
from pydantic import BaseModel, Field
from enum import Enum

MetodoPago = Literal["efectivo", "tarjeta", "transferencia"]
Rol = Literal["superadmin", "cajero"]
EstadoPago = Literal["AL_DIA", "ATRASADO"]


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
    nuevo_precio: float = Field(ge=0)


class ProductoNuevo(BaseModel):
    codigo_barras: str | None = None
    nombre_producto: str
    precio_sugerido: float = Field(ge=0)
    precio_costo: float | None = Field(default=None, ge=0)
    stock_actual: float = Field(default=0, ge=0)
    stock_minimo: float = Field(default=0, ge=0)
    proveedor: str | None = None
    fecha_caducidad: str | None = None
    unidad_medida: str = "pieza"
    controla_stock: bool = True


class ActualizacionProducto(BaseModel):
    nombre_producto: str
    precio_sugerido: float = Field(ge=0)
    precio_costo: float | None = Field(default=None, ge=0)
    stock_actual: float = Field(ge=0)
    stock_minimo: float = Field(ge=0)
    proveedor: str | None = None
    codigo_barras: str | None = None
    fecha_caducidad: str | None = None
    unidad_medida: str = "pieza"
    controla_stock: bool | None = None
    stock_anterior: float | None = None  # #75: stock que mostraba el formulario; si viene, se aplica la diferencia


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
    cantidad: float = Field(gt=0)
    fecha_caducidad: str | None = None
    precio_costo: float | None = Field(default=None, ge=0)


class EntradaLote(BaseModel):
    items: list[ItemEntradaLote]
    nota_general: str | None = None


class ClienteNuevo(BaseModel):
    nombre: str
    telefono: str | None = None
    limite_credito: float | None = Field(default=None, ge=0)


class LimiteCredito(BaseModel):
    limite_credito: float | None = Field(default=None, ge=0)


class NombreCliente(BaseModel):
    nombre: str


class ItemFiado(BaseModel):
    id_cuenta: int
    id_turno: int
    producto: str
    cantidad: float = 1.0
    precio: float
    monto_real: float | None = None


class ItemFiadoLote(BaseModel):
    producto: str
    cantidad: float = Field(default=1.0, ge=0)
    precio: float = Field(ge=0)
    monto_real: float | None = Field(default=None, ge=0)
    id_producto: int | None = None


class FiadoLote(BaseModel):
    id_cuenta: int
    id_turno: int
    items: list[ItemFiadoLote]


class AbonoFiado(BaseModel):
    id_cuenta: int
    id_turno: int
    monto: float = Field(gt=0)
    nota: str | None = None
    metodo_pago: MetodoPago = "efectivo"


class ItemVenta(BaseModel):
    producto: str
    cantidad: float = Field(default=1.0, ge=0)
    precio_unitario: float = Field(ge=0)
    id_producto: int | None = None
    cantidad_real: float | None = Field(default=None, ge=0)


class VentaLote(BaseModel):
    id_turno: int
    items: list[ItemVenta]
    metodo_pago: MetodoPago = "efectivo"


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


class GastoFijo(BaseModel):
    nombre: str
    monto: float = Field(ge=0)


class ConfiguracionTicket(BaseModel):
    reglas: List[ReglaResumen] = []
    gastos_fijos: List[GastoFijo] = []


class TiendaNueva(BaseModel):
    nombre_comercial: str


class UsuarioNuevo(BaseModel):
    username: str
    password: str
    id_tienda: int
    rol: Rol = "cajero"


class ResetPassword(BaseModel):
    nuevo_password: str


class CambioPassword(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=6, max_length=72)


class ActualizacionNombreTienda(BaseModel):
    nombre_comercial: str


class ActualizacionUsuario(BaseModel):
    id_tienda: int
    rol: Rol


class SuscripcionTienda(BaseModel):
    dia_corte: int
    monto_mensual: float
    estado_pago: EstadoPago