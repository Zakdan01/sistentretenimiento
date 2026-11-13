# Caso de Estudio 2 — Biblioteca virtual

Catálogo de películas, series y anime con perfiles de usuario y biblioteca
personal. MongoDB como base documental y Redis para sesión, cache, ranking y
contadores.

## Requisitos

- Python 3.12 o superior
- MongoDB local en `mongodb://localhost:27017`
- Redis local en `redis://localhost:6379`

## Puesta en marcha

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m flask --app app.run run
```

La aplicación queda en `http://127.0.0.1:5000` y el chequeo de salud en
`/health`.

## Estructura

- `app/` — sistema Flask (rutas, servicios, plantillas).
- `mongodb/` — inicialización, seed, consultas y agregaciones.
- `redis/` — mapa de claves y scripts de apoyo.
- `docs/` — diagramas y capturas para el informe.

## Pruebas

```powershell
python -m pytest -q
```
