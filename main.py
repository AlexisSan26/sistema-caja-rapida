import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from auth import register_auth_routes, register_yo_route, limiter
from routers import turnos, ventas, inventario, entradas, fiados, config, admin

load_dotenv()

app = FastAPI()

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://alexissan26.github.io/sistema-caja-rapida/").split(",")
ALLOWED_ORIGINS += ["http://localhost:63342", "http://127.0.0.1:63342", "http://localhost:5500", "http://127.0.0.1:5500"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ─── Registro de rutas ────────────────────────────────────────────────────────
register_auth_routes(app)
register_yo_route(app)

app.include_router(turnos.router)
app.include_router(ventas.router)
app.include_router(inventario.router)
app.include_router(entradas.router)
app.include_router(fiados.router)
app.include_router(config.router)
app.include_router(admin.router)


# ─── Endpoints base ───────────────────────────────────────────────────────────
@app.get("/despertar")
async def despertar():
    return {"estado": "despierto", "mensaje": "Servidor listo para el turno"}


@app.get("/")
def inicio():
    return {"mensaje": "API del Sistema de Caja SaaS funcionando"}