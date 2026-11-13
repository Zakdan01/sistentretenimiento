# AGENTS.md

Aplicación Flask + Jinja de biblioteca virtual (películas, series y anime).
MongoDB es la fuente de verdad; Redis aporta sesiones, cache, contadores y
ranking. El informe de `docs/` es un entregable central, no un extra.

## Comandos

Usar siempre el venv del repo (Python 3.14.7); `python` a secas puede apuntar a otro intérprete.

```powershell
.\.venv\Scripts\python -m flask --app app.run run   # http://127.0.0.1:5000, salud en /health
.\.venv\Scripts\python -m pytest -q                  # suite completa (~6 min, 121 pruebas)
.\.venv\Scripts\python -m pytest tests/test_catalog_search.py::test_search_filters_by_type -q
```

Inicialización y datos (Mongo en `localhost:27017`, Redis en `localhost:6379`):

```powershell
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/01_collections.js
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/02_indexes.js
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/03_drop_legacy.js  # solo si existe `titles`
.\.venv\Scripts\python -m mongodb.seed.load_seed --reset
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/queries/report_queries.js
```

Regenerar el catálogo (requiere red y puede tardar por los límites de Wikimedia):

```powershell
.\.venv\Scripts\python -m mongodb.seed.fetch_catalog --limit 500 --candidates 1500 --years 1990-2025
.\.venv\Scripts\python -m mongodb.seed.build_demo
```

No hay lint, typecheck, formateador ni CI configurados: la verificación es `pytest`.
No hay remoto git configurado; no intentes `git push`.

## Pruebas: gotchas que cuestan tiempo

- Usan **MongoDB y Redis reales**, no mocks. `mongosh` debe estar en `PATH`.
- No existe `conftest.py`: `tests/support.py` concentra el catálogo determinístico
  de 16 títulos, la inicialización de Mongo/Redis y las factories. Cada módulo
  de pruebas conserva sus fixtures, crea una base `catalogo_test_*`, corre los dos
  scripts de `mongodb/init/` y hace `flushdb` en Redis DB 15.
- **Nunca corras dos procesos de pytest a la vez.** Comparten Redis DB 15 y en Windows
  provocan una excepción fatal de pymongo/hang que parece un cuelgue del test.
- La suite completa tarda ~6 min por la inicialización de Mongo/Redis y los
  scripts JS; no está colgada.
- Redis 5.0.14.1 (build Windows) no soporta RESP3. El cliente se crea con `protocol=2`;
  no lo cambies ni introduzcas Flask-Session (arrastra `msgspec` en Python 3.14).
- Las pruebas de reportes ejecutan los `.js` y parsean su stdout. Los scripts de
  `mongodb/aggregations/` y `mongodb/queries/` deben imprimir JSON con
  `JSON.stringify(...)`, no `printjson`.

## Modelo y datos

- La base `catalogo` tiene exactamente cinco colecciones: `users`, `movies`,
  `series`, `animes` y `library_entries`. No debe existir `titles` ni una base
  paralela tipo `catalogo_v2`.
- Las tres colecciones de catálogo comparten forma (`external`, `type`, `title`,
  `poster_url`, `synopsis`, `year`, `genres`, `external_rating`, `created_at`,
  `updated_at`) y cada una acepta un solo `type`.
- `library_entries` referencia `user_id` y `title_id`, y guarda `title_type`
  obligatorio para resolver la colección sin recorrer las tres. No dupliques la
  ficha dentro de la entrada.
- Los validadores usan `additionalProperties: false`: todo campo nuevo debe declararse
  en `mongodb/init/01_collections.js` (incluido `_id`) o las escrituras fallan.
- Los índices de texto se llaman `text_busqueda` en cada colección, usan
  `default_language: "spanish"` y `02_indexes.js` los borra antes de crearlos. Un
  `createIndex` sobre el existente no cambia sus opciones.
- El índice único `uq_fuente_externa` es parcial (`external` de tipo objeto):
  los títulos manuales con `external: null` no participan.
- Seed e importación son idempotentes por `external.source + external.id` con
  `update_one(upsert)`/`bulk_write` y `$setOnInsert` para `created_at`. Usuarios
  por email y bibliotecas por `user_id + title_id`. No insertes títulos por `_id`
  ni rompas esa identidad.
- Los JSON de `mongodb/seed/data/` solo llevan `source`, `external_id`, `title`,
  `image`, `synopsis`, `year`, `genres` y `rating`. `load_seed.py` completa el
  esquema; `build_demo.py` genera las bibliotecas.
- Las pruebas usan el catálogo de 16 títulos de `tests/support.py` (5 películas,
  5 series, 6 animes) y afirman conteos exactos. Si editás `CATALOG`, revisá
  `test_seed.py`, `test_mongo_init.py`, `test_reports.py` y las pruebas de catálogo.
- Las claves de cache se namespacean por base Mongo (`cache:*:<db>:*`) para no mezclar
  producción y pruebas. Conservá ese namespace al agregar claves. TTL: búsqueda 60 s,
  ficha 300 s, API externa 600 s.
- La sesión es propia: hash `sess:<sid>` en Redis + cookie `sid` HttpOnly. No es
  Flask-Session. `users.role` es `admin` o `user`; el panel usa `admin_required`.

## Arquitectura

- `app/__init__.py` expone `create_app()`; `app/run.py` es el entrypoint de Flask.
- Blueprints: `auth` (incluye `profile`), `catalog`, `library` y `admin`.
- Las rutas son delgadas; la lógica de dominio vive en `app/*/services.py`.
  `catalog/providers.py` normaliza Jikan/TMDB, `catalog/importer.py` hace el upsert,
  `admin/services.py` concentra el CRUD y los reportes, y `app/cache.py` centraliza Redis.
- APIs JSON: `/api/search`, `/api/titles/<id>`, `/api/popular`.
- El panel `/admin` permite crear, editar y eliminar títulos y usuarios, y ver
  dashboard y reportes. Al borrar un título se eliminan sus entradas de
  biblioteca; al borrar un usuario, su biblioteca. No se puede eliminar la propia
  cuenta ni degradar al último administrador.

## Entorno y documentación

- Copiá `.env.example` a `.env`. Los defaults funcionan en local; `TMDB_API_KEY` es
  opcional y sin ella TMDB falla con un error controlado.
- La generación del catálogo sale a Wikipedia, Wikidata e IMDb. La importación en
  vivo de Jikan/TMDB no se puede verificar sin red: usá payloads grabados o
  monkeypatch como en `tests/test_providers.py` y `tests/test_import_routes.py`.
- La consola de Windows muestra mal los acentos. Para scripts que imprimen texto en
  español usá `$env:PYTHONUTF8=1`; los datos en Mongo/Redis ya son UTF-8 correctos.
- Mantené sincronizados `docs/informe.md` (secciones 1–9), `mongodb/README.md`,
  `redis/README.md` y este archivo cuando cambien rutas, claves, índices,
  credenciales demo o el número de pruebas.
