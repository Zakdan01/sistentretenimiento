# Caso de Estudio 2 — Biblioteca virtual

Catálogo de películas, series y anime con perfiles de usuario, biblioteca
personal y panel de administración. MongoDB como base documental (cinco
colecciones) y Redis para sesión, cache, ranking y contadores.

## Requisitos

- Python 3.14
- MongoDB local en `mongodb://localhost:27017`
- Redis local en `redis://localhost:6379`
- `mongosh` en el `PATH` para inicializar la base y correr los reportes

## Puesta en marcha

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env

mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/01_collections.js
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/02_indexes.js
.\.venv\Scripts\python -m mongodb.seed.load_seed --reset

.\.venv\Scripts\python -m flask --app app.run run
```

La aplicación queda en `http://127.0.0.1:5000` y el chequeo de salud en
`/health`. El panel de administración está en `/admin`.

### Cuentas demo

| Email | Contraseña | Rol |
| --- | --- | --- |
| `admin@biblioteca.local` | `Admin12345` | admin |
| `laura@biblioteca.local` | `Laura12345` | user |
| `diego@biblioteca.local` | `Diego12345` | user |

## Estructura

- `app/` — sistema Flask (rutas, servicios, plantillas), incluido `app/admin/`.
- `mongodb/` — inicialización, generación y carga del seed, consultas y
  agregaciones.
- `redis/` — mapa de claves y notas de operación.
- `docs/` — informe con diagramas y resultados.
- `tests/` — suite de integración con MongoDB y Redis reales.

## Pruebas

```powershell
.\.venv\Scripts\python -m pytest -q
```

La suite usa MongoDB y Redis reales, crea bases `catalogo_test_*`, usa la base
15 de Redis y necesita `mongosh` en el `PATH`. No ejecutar dos procesos de
pytest a la vez.
