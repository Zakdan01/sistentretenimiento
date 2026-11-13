# MongoDB en la biblioteca virtual

MongoDB es la fuente de verdad del sistema. Guarda usuarios, el catálogo local
(copia de los títulos importados desde Jikan/TMDB) y las entradas de biblioteca
de cada usuario.

## Colecciones

### `users`

Un documento por cuenta. El email es único mediante índice.

| Campo | Tipo | Notas |
| --- | --- | --- |
| `_id` | ObjectId | identidad |
| `email` | string | único, normalizado a minúsculas |
| `password_hash` | string | PBKDF2 de Werkzeug |
| `display_name` | string | 1–60 caracteres |
| `avatar_url` | string o null | reservado para la interfaz |
| `created_at` | date | alta |

### `titles`

Catálogo polimórfico: `type` es `movie`, `series` o `anime`. Los campos de
temporadas y episodios se embeben porque se consultan junto con la ficha y no
crecen sin límite (una serie tiene decenas de temporadas como máximo).

| Campo | Tipo | Notas |
| --- | --- | --- |
| `external` | objeto | `{source: "tmdb"|"jikan", id}` único compuesto |
| `type` | enum | `movie`, `series`, `anime` |
| `title`, `original_title` | string | búsqueda con pesos |
| `synopsis` | string | texto libre |
| `genres` | array de string | facetas |
| `release_date`, `year` | date, int | filtros por año |
| `runtime_minutes` | int o null | películas |
| `seasons` | array de `{number, episodes, air_date?}` | series y anime |
| `episodes_total` | int o null | series y anime |
| `directors`, `cast`, `studios` | arrays de string | búsqueda y ficha |
| `poster_url` | string o null | imagen remota |
| `external_rating` | double o null | valoración de la fuente |
| `awards` | array de string | ficha |
| `created_at`, `updated_at` | date | auditoría |

### `library_entries`

Relación entre usuario y título con estado, favorito, nota y progreso. Se
referencia el título (`title_id`) en lugar de copiarlo: el catálogo cambia con
las importaciones y no debe duplicarse por usuario.

| Campo | Tipo | Notas |
| --- | --- | --- |
| `user_id`, `title_id` | ObjectId | índice único compuesto |
| `status` | enum | `watching`, `watched`, `planned`, `dropped` |
| `favorite` | bool | “me gusta” |
| `rating` | int o null | 1–10 |
| `progress` | `{season, episode}` o null | avance |
| `notes` | string o null | hasta 500 caracteres |
| `created_at`, `updated_at` | date | auditoría |

## Índices

Definidos en `mongodb/init/02_indexes.js`, idempotente.

| Colección | Índice | Uso |
| --- | --- | --- |
| `titles` | `text_busqueda` (texto español, pesos) | búsqueda libre |
| `titles` | `tipo_anio` (`type`, `year` desc) | facetas y orden |
| `titles` | `tipo_genero` (`type`, `genres`) | filtro por género |
| `titles` | `anio` (`year` desc) | orden por año |
| `titles` | `valoracion_externa` (`external_rating` desc) | orden por nota |
| `titles` | `uq_fuente_externa` (`external.source`, `external.id`) único | idempotencia de importación |
| `users` | `uq_email` único | login y alta |
| `library_entries` | `uq_usuario_titulo` único | un estado por usuario/título |
| `library_entries` | `usuario_estado` | listado por estado |
| `library_entries` | `titulo_estado` | estadísticas por título |
| `library_entries` | `usuario_favoritos` (parcial `favorite: true`) | favoritos |

## Puesta en marcha

```powershell
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/01_collections.js
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/02_indexes.js
python -m mongodb.seed.load_seed
```

El seed carga 16 títulos (4 películas, 5 series, 7 anime) y es idempotente:
usa `update_one(upsert)` por `external.source + external.id`.

## Importación desde APIs

```powershell
python -m mongodb.seed.import_external jikan 21 38000 31964
python -m mongodb.seed.import_external tmdb 27205 --media-type movie
```

TMDB requiere `TMDB_API_KEY` en `.env`. Jikan no requiere clave, pero limita a
3 pedidos por segundo.

## Agregaciones del informe

En `mongodb/aggregations/`:

| Archivo | Reporte |
| --- | --- |
| `01_top_genres.js` | géneros por cantidad y nota media |
| `02_library_by_status.js` | actividad por usuario y estado |
| `03_catalog_health.js` | volumen, nota media y episodios por tipo |
| `04_user_activity.js` | usuarios más activos, favoritos y nota media |
| `05_top_rated_by_type.js` | top 3 por tipo con `$setWindowFields` |

## Consultas y dimensionamiento

```powershell
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/queries/report_queries.js
mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/queries/sizing.js
```

`report_queries.js` imprime `stage`, `nReturned`, `totalKeysExamined`,
`totalDocsExamined` y `executionTimeMillis` de las consultas principales.
`nReturned == totalKeysExamined == totalDocsExamined` indica que el índice
cubrió la selectividad sin examinar documentos de más.

## Decisiones de modelado

- **Embedding** de temporadas y elenco dentro de `titles`: se leen siempre con
  la ficha, tienen tamaño acotado y no se actualizan por separado.
- **Referencias** desde `library_entries` a `users` y `titles`: la biblioteca
  es una relación N:M y el título es una entidad con vida propia.
- **Unicidad** de `external.source + external.id` para que la importación sea
  idempotente y para que un título no se duplique entre ejecuciones.
- **Validadores JSON Schema** en las tres colecciones; `additionalProperties:
  false` en `titles` y `library_entries` obliga a declarar cada campo nuevo.
