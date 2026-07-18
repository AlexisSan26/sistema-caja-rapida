\# Alta de cliente nuevo (tienda) — Caja Rápida



Checklist para dar de alta una tienda nueva en producción. Requiere estar logueado

como `superadmin` en `admin.html`.



\## Paso 1 — Crear la tienda

`POST /admin/tiendas`

```json

{ "nombre\_comercial": "Nombre de la tienda" }

```

Se crea con `activa = 1` automáticamente. Guarda el `id\_tienda` que devuelve la

respuesta — lo necesitas en los siguientes pasos.



\## Paso 2 — Crear el primer usuario (cajero)

`POST /admin/usuarios`

```json

{

&#x20; "username": "usuario\_tienda",

&#x20; "password": "contraseña\_temporal",

&#x20; "id\_tienda": 0,

&#x20; "rol": "cajero"

}

```

> El rol solo acepta `"superadmin"` o `"cajero"` hoy — no existe el rol "dueño"

> todavía (ver roadmap #24). El primer usuario de toda tienda nueva es cajero.



\## Paso 3 — Configurar la suscripción

`PUT /admin/tiendas/{id\_tienda}/suscripcion`

```json

{

&#x20; "dia\_corte": 1,

&#x20; "monto\_mensual": 199.00,

&#x20; "estado\_pago": "AL\_DIA"

}

```

\*\*No te saltes este paso.\*\* No hay un `.sql` de esquema en el repo que confirme

los defaults de estas columnas si la tienda se queda sin suscripción configurada —

mejor configurarla siempre en el alta, nunca asumir el default de la tabla.



\## Paso 4 — Verificar

\- Inicia sesión con el usuario/contraseña del paso 2 en `index.html` (confirmar

&#x20; que usan `index.html`, no `index\_v2.html` — ver pendiente #9 del roadmap).

\- Confirma que el nombre de la tienda aparece correcto en el ticket.

\- Entrega las credenciales al cliente y pídele que cambie la contraseña desde

&#x20; su primer acceso si el sistema ya lo permite (si no, queda como mejora futura).



\## Notas

\- El catálogo de productos arranca vacío por tienda. Al escanear un código de

&#x20; barras que ya existe en `productos\_globales` (tabla compartida entre tiendas),

&#x20; el sistema autocompleta nombre y unidad — no es necesario precargar catálogo

&#x20; manualmente.

\- La configuración del ticket (`/configuracion\_tienda`) la hace el propio

&#x20; usuario de la tienda una vez que inicia sesión — no es parte del alta que tú

&#x20; haces como superadmin.

