\# Caja Rápida



Sistema de punto de venta (POS) multi-tenant en modalidad SaaS para tiendas de retail pequeño en México. Suscripción mensual, catálogo de productos, ventas, fiados, turnos de caja, corte de caja y panel de superadministración para dar de alta y gestionar tiendas clientes.



\## Stack



\- \*\*Backend:\*\* FastAPI (Python)

\- \*\*Frontend:\*\* HTML + CSS + JavaScript vanilla (sin build step)

\- \*\*Base de datos:\*\* MySQL (hosteada en Aiven)

\- \*\*Hosting backend:\*\* Render

\- \*\*Hosting frontend:\*\* GitHub Pages



\## Arquitectura



```

main.py            → arranque de la app, CORS, rate limiting, registro de routers

database.py         → pool de conexiones MySQL (mysql-connector-python)

auth.py              → login, JWT, validación de sesión, invalidación por token\_version

models.py            → esquemas Pydantic (requests/responses)

helpers.py           → utilidades compartidas: caché de auth, log de auditoría, cálculo de resumen de turno

routers/

&#x20; turnos.py          → apertura, cierre y consulta de turnos de caja

&#x20; ventas.py           → registro de movimientos (ventas, retiros, fondo de caja)

&#x20; inventario.py        → productos, búsqueda, mermas

&#x20; entradas.py          → entradas de mercancía / resurtido

&#x20; fiados.py             → clientes a crédito, abonos, cuentas fiado

&#x20; config.py              → configuración de reglas del ticket por tienda

&#x20; admin.py                → panel de superadmin: alta/gestión de tiendas y usuarios

```



Cada tabla relevante lleva `id\_tienda`, y cada endpoint protegido filtra por el `id\_tienda` que viene en el JWT del usuario autenticado — ese es el mecanismo de aislamiento multi-tenant. \*\*No existe todavía una capa que fuerce ese filtro a nivel de código\*\* (ver punto #29 del roadmap); el aislamiento depende de que cada query lo aplique explícitamente, así que cualquier query nueva en `routers/` debe incluir `WHERE id\_tienda = %s` (o el JOIN equivalente) sin excepción.



\### Autenticación



\- Login devuelve un JWT (`HS256`) con `id\_tienda`, `id\_usuario`, `rol` y `token\_version`.

\- `get\_current\_user` (en `auth.py`) valida el token, y además vuelve a leer `rol` y `token\_version` desde la base de datos en cada request (con una caché en memoria de 5 minutos vía `TTLCache`) — así, si a un usuario le cambian el rol o la tienda, su sesión anterior queda invalidada aunque el JWT siga siendo válido.

\- Los tokens de cajero expiran a los 30 días; los de superadmin, a los 2 días.

\- Si el `estado\_pago` de la tienda es `ATRASADO`, todos los endpoints protegidos devuelven `402` — excepto para el rol `superadmin`, que nunca queda bloqueado de su propio panel.



\### Frontend



El frontend es estático (GitHub Pages) y detecta automáticamente si corre en local o producción (`js/api.js`), apuntando a `http://127.0.0.1:8000` o a la URL de Render según el hostname. El JWT se guarda en `localStorage`.



\## Requisitos



\- Python 3.11+

\- Una base de datos MySQL accesible (por ejemplo, un servicio de Aiven o una instancia local)



\## Instalación local



```bash

git clone https://github.com/AlexisSan26/sistema-caja-rapida.git

cd sistema-caja-rapida

python -m venv venv

source venv/bin/activate      # en Windows: venv\\Scripts\\activate

pip install -r requirements.txt

```



Crea un archivo `.env` en la raíz del proyecto con las variables de entorno de la siguiente sección, y luego levanta el servidor:



```bash

uvicorn main:app --reload

```



La API queda disponible en `http://127.0.0.1:8000`. Con `ENV=development`, `/docs` y `/openapi.json` se habilitan automáticamente; en producción quedan deshabilitados por diseño (ver `main.py`).



Para el frontend, basta con abrir `index.html` con un servidor estático local (por ejemplo, la extensión Live Server de VS Code en el puerto `5500`, o `127.0.0.1:63342` de PyCharm) — esos orígenes ya están permitidos en CORS junto con el de producción.



\## Variables de entorno



| Variable | Requerida | Descripción |

|---|---|---|

| `DB\_HOST` | Sí | Host del servidor MySQL |

| `DB\_PORT` | No (default `28257`) | Puerto del servidor MySQL |

| `DB\_USER` | Sí | Usuario de la base de datos |

| `DB\_PASSWORD` | Sí | Contraseña de la base de datos |

| `DB\_NAME` | Sí | Nombre de la base de datos |

| `SECRET\_KEY` | Sí | Clave secreta para firmar los JWT. Sin esta variable, la app no arranca (falla explícitamente en `auth.py`) |

| `ENV` | No (default `production`) | `development` habilita `/docs`, `/redoc` y `/openapi.json` |

| `ALLOWED\_ORIGINS` | No (default `https://alexissan26.github.io/sistema-caja-rapida/`) | Orígenes permitidos por CORS, separados por coma. Los orígenes de desarrollo local (`localhost:5500`, `127.0.0.1:63342`, etc.) ya están agregados en código y no necesitan declararse aquí |



La conexión a MySQL usa SSL obligatorio (`ssl\_disabled: False`) y zona horaria fija `-06:00`, pensado para el hosting en Aiven — si se apunta a otra base, confirma que soporte SSL o ajusta `database.py`.



\## Despliegue



\- \*\*Backend:\*\* Render, con las variables de entorno de arriba configuradas en el dashboard del servicio.

\- \*\*Frontend:\*\* GitHub Pages, sirviendo directamente `index.html` desde la raíz del repo.

\- \*\*Base de datos:\*\* Aiven (MySQL), con backup automático activo y retención de 3 días.



\## Estado del proyecto



El desarrollo se guía por un roadmap interno priorizado por riesgo (seguridad y datos primero, luego deuda técnica, luego features). No está incluido en este repo público.

