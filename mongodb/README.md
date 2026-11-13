# MongoDB en la biblioteca virtual

MongoDB es la fuente de verdad del sistema. Guarda usuarios, el catálogo local
(copia de los títulos generados desde Wikipedia/Wikidata/IMDb e importados desde
Jikan/TMDB) y las entradas de biblioteca de cada usuario.

## Colecciones

La base `catalogo` tiene exactamente cinco colecciones: `users`, `movies`,
`series`, `animes` y `library_entries`.

### `users`

Un documento por cuenta. El email es único mediante índice; `role` distingue al
administrador del usuario común.

| Campo | Tipo | Notas |
| --- | --- | --- |
| `_id` | ObjectId | identidad |
| `email` | string | único, normalizado a minúsculas |
| `password_hash` | string | PBKDF2 de Werkzeug |
| `display_name` | string | 1–60 caracteres |
| `role` | enum | `admin` o `user` |
| `avatar_url` | string o null | reservado para la interfaz |
| `created_at` | date | alta |

### `movies`, `series` y `animes`

Las tres comparten la misma forma; cada colección acepta un solo `type`. Se
separaron para que los validadores sean estrictos (una película no puede quedar
en `series`) y para que los índices de texto y de facetas sean homogéneos.

| Campo | Tipo | Notas |
| --- | --- | --- |
| `_id` | ObjectId | identidad |
| `external` | objeto o null | `{source: "imdb"|"tmdb"|"jikan"|"anilist"|"manual", id}` único por colección |
| `type` | enum | `movie`, `series` o `anime`, fijo por colección |
| `title` | string | búsqueda con peso alto |
| `synopsis` | string | texto libre |
| `year` | int o null | 1900–2100 |
| `genres` | array de string | facetas |
| `poster_url` | string o null | imagen remota |
| `external_rating` | double o null | nota de la fuente (0–10) |
| `created_at`, `updated_at` | date | auditoría |

Los títulos cargados a mano desde el panel tienen `external: null`; el resto se
identifica por `external.source + external.id`.

### `library_entries`

Relación entre usuario y título con estado, favorito, nota y progreso. Se
referencia el título (`title_id`) en lugar de copiarlo: el catálogo cambia con
las importaciones y no debe duplicarse por usuario. `title_type` indica en qué
colección vive el título y evita recorrer las tres al resolver la ficha.

| Campo | Tipo | Notas |
| --- | --- | --- |
| `user_id`, `title_id` | ObjectId | índice único compuesto |
| `title_type` | enum | `movie`, `series` o `anime` |
| `status` | enum | `watching`, `watched`, `planned`, `dropped` |
| `favorite` | bool | “me gusta” |
| `rating` | int o null | 1–10 |
| `progress` | `{season, episode}` o null | avance |
| `notes` | string o null | hasta 500 caracteres |
| `created_at`, `updated_at` | date | auditoría |

## Índices

Definidos en `mongodb/init/02_indexes.js`, idempotente. Los índices de catálogo
se repiten en `movies`, `series` y `animes`.

| Colección | Índice | Uso |
| --- | --- | --- |
| catálogo | `text_busqueda` (texto español, pesos 10/3/1) | búsqueda libre |
| catálogo | `anio` (`year` desc) | orden por año |
| catálogo | `genero_anio` (`genres`, `year` desc) | filtro por género |
| catálogo | `valoracion_externa` (`external_rating` desc) | orden por nota |
| catálogo | `uq_fuente_externa` (`external.source`, `external.id`) único parcial | idempotencia de importación |
| `users` | `uq_email` único | login y alta |
| `users` | `rol` | listados y métricas del panel |
| `library_entries` | `uq_usuario_titulo` único | un estado por usuario/título |
| `library_entries` | `usuario_estado` | listado por estado |
| `library_entries` | `titulo_estado` | estadísticas por título |
| `library_entries` | `usuario_favoritos` (parcial `favorite: true`) | favoritos |
| `library_entries` | `tipo_titulo` | resolución por colección |

El índice único de identidad externa es **parcial** (`external` de tipo objeto):
los títulos manuales con `external: null` no participan y pueden convivir.

## Puesta en marcha

```powershell
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/01_collections.js
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/02_indexes.js

# Solo si venís de la versión con la colección `titles`
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/03_drop_legacy.js

python -m mongodb.seed.load_seed --reset
```

`--reset` borra catálogo, usuarios y bibliotecas antes de cargar. Sin `--reset`
el seed es idempotente: usa `update_one(upsert)` por `external.source +
external.id` (catálogo), email (usuarios) y `user_id + title_id` (bibliotecas).

### Datos del seed

```text
mongodb/seed/
├─ fetch_catalog.py     # genera data/{movies,series,animes}.json desde Wikipedia/Wikidata/IMDb
├─ build_demo.py        # genera data/libraries.json a partir del catálogo
├─ load_seed.py         # carga catálogo, usuarios y bibliotecas en MongoDB
└─ data/
   ├─ movies.json
   ├─ series.json
   ├─ animes.json
   ├─ users.json        # 1 admin + 2 usuarios demo
   └─ libraries.json    # bibliotecas de ejemplo
```

Los JSON de catálogo solo contienen `source`, `external_id`, `title`, `image`,
`synopsis`, `year`, `genres` y `rating`; el esquema de MongoDB lo completa el
loader.

Cuentas demo (`data/users.json`):

| Email | Contraseña | Rol |
| --- | --- | --- |
| `admin@biblioteca.local` | `Admin12345` | admin |
| `laura@biblioteca.local` | `Laura12345` | user |
| `diego@biblioteca.local` | `Diego12345` | user |

### Regenerar el catálogo (requiere red)

```powershell
python -m mongodb.seed.fetch_catalog --limit 500 --candidates 1500 --years 1990-2025
python -m mongodb.seed.build_demo
```

El generador consulta categorías de Wikipedia en español por año, enriquece con
Wikidata (`P345`, `P136`, `P577`), completa pósters desde la Wikipedia inglesa
y toma las notas de `title.ratings.tsv.gz` de IMDb. Reintenta ante 429 y respeta
`Retry-After`.

## Importación desde APIs

```powershell
python -m mongodb.seed.import_external jikan 21 38000 31964
python -m mongodb.seed.import_external tmdb 27205 --media-type movie
```

TMDB requiere `TMDB_API_KEY` en `.env`. Jikan no requiere clave, pero limita a
3 pedidos por segundo. La importación es idempotente y elige la colección según
el `type` del payload.

## Agregaciones del informe

En `mongodb/aggregations/`:

| Archivo | Reporte |
| --- | --- |
| `01_top_genres.js` | géneros por cantidad y nota media |
| `02_library_by_status.js` | actividad por usuario y estado |
| `03_catalog_health.js` | volumen, nota media e imágenes por tipo |
| `04_user_activity.js` | usuarios más activos, favoritos y nota media |
| `05_top_rated_by_type.js` | top 3 por tipo con `$setWindowFields` |

## Consultas y dimensionamiento

```powershell
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/queries/report_queries.js
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/queries/sizing.js
```

`report_queries.js` imprime `stage`, `nReturned`, `totalKeysExamined`,
`totalDocsExamined` y `executionTimeMillis` de las consultas principales.
`sizing.js` recorre todas las colecciones y reporta documentos, tamaño medio,
almacenamiento e índices.

## Decisiones de modelado

- **Una colección por tipo** (`movies`, `series`, `animes`): validadores
  estrictos, documentos homogéneos e índices equivalentes en las tres.
- **Referencias** desde `library_entries` a `users` y a la colección del
  título: la biblioteca es una relación N:M y el título es una entidad con vida
  propia.
- **`title_type` desnormalizado** en la entrada para resolver la ficha con un
  `find_one` en la colección correcta.
- **Unicidad** de `external.source + external.id` por colección para que la
  importación sea idempotente.
- **Validadores JSON Schema** en las cinco colecciones; `additionalProperties:
  false` obliga a declarar cada campo nuevo.
