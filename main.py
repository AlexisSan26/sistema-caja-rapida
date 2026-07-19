import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from auth import register_auth_routes, register_yo_route, limiter
from routers import turnos, ventas, inventario, entradas, fiados, config, admin

load_dotenv()

ENV = os.getenv("ENV", "production")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Caja Rápida API",
    docs_url="/docs" if ENV == "development" else None,
    redoc_url="/redoc" if ENV == "development" else None,
    openapi_url="/openapi.json" if ENV == "development" else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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