# Tests de aislamiento multi-tenant (#12)

Estos tests verifican que una tienda **nunca** pueda ver, editar o borrar datos
de otra tienda — ni por listados, ni adivinando IDs. Corren contra un schema
de MySQL local **nuevo y vacío**, así que no tocan ni tu base restaurada ni
Aiven (producción).

## Requisito previo

Necesitas tu MySQL local corriendo (el mismo que usaste en la prueba de
restore del #10), con una base ya restaurada — la usamos únicamente para
clonar la *estructura* de las tablas (no los datos).

## Instalación (una sola vez)

```bash
pip install -r requirements-dev.txt --break-system-packages
```
(en Windows, sin `--break-system-packages`)

## Cómo correrlo

```bash
pytest tests/ -v
```

Por default asume que tu base local restaurada se llama `defaultdb` (el
mismo nombre que Aiven). Si le pusiste otro nombre, agrega esto a tu `.env`:

```
TEST_SOURCE_SCHEMA=nombre_real_de_tu_schema_local
```

## Qué hace exactamente

1. Crea un schema nuevo llamado `caja_rapida_test` en tu MySQL local.
2. Clona ahí la estructura de tablas (sin datos) de tu schema restaurado.
3. Crea 2 tiendas de prueba falsas (A y B), cada una con su propio cajero,
   usando la API real (igual que en producción).
4. Corre cada escenario: A intenta ver/editar/borrar algo de B, y el test
   falla si lo logra.
5. Al terminar, borra `caja_rapida_test` automáticamente.

Si quieres inspeccionar los datos de prueba a mano en Workbench después de
una corrida (por ejemplo si un test falló y quieres ver por qué), corre:

```bash
KEEP_TEST_DB=1 pytest tests/ -v
```

y el schema `caja_rapida_test` se queda ahí hasta que lo borres tú mismo.

## Si un test falla

Un test rojo aquí significa una fuga real entre tiendas — trátalo como el
bug de mayor prioridad, por encima de cualquier feature nueva en curso.
