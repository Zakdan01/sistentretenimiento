# Caso de Estudio 2 — Biblioteca virtual de películas, series y anime

**Materia:** Base de Datos 3
**Dupla 14:** Laura Mamani, Ivan Rios
**Stack:** Flask + Jinja, MongoDB 8.3, Redis 5.0
**Repositorio:** aplicación en `app/`, modelado en `mongodb/`, claves y notas de Redis en `redis/`

---

## 1. Introducción

El trabajo desarrolla una aplicación web de biblioteca virtual para películas,
series y anime. Un visitante puede explorar el catálogo, buscar por texto libre
y filtrar por tipo, género, año y valoración; un usuario registrado puede
guardar títulos en su biblioteca personal con un estado de seguimiento
(viendo, vista, pendiente, abandonada), marcarlos como favoritos, puntuarlos de
1 a 10 y registrar su progreso por temporada y episodio.

El catálogo no se carga a mano: se importa desde APIs externas (TMDB para
películas y series, Jikan para anime) y se guarda una copia local en MongoDB.
MongoDB es la fuente de verdad; Redis se usa para sesiones, cache de consultas,
contadores y ranking de popularidad.

La entrega prioriza el **modelado NoSQL y el análisis de decisiones** por sobre
la cantidad de funcionalidades. Por eso la aplicación es deliberadamente
pequeña y cada pantalla existe para ejercitar una decisión de modelado:
documentos embebidos, referencias, índices, validadores, agregaciones y
cache-aside.

---

## 2. Contexto

El caso se enmarca en la materia Base de Datos 3, donde se estudian bases de
datos NoSQL orientadas a documentos y clave-valor. La consigna pide:

- una aplicación web con Flask y plantillas Jinja (sin SPA);
- MongoDB y Redis como únicas bases de datos;
- tres carpetas diferenciadas: `app/`, `mongodb/` y `redis/`;
- importación de títulos desde una API externa, con copia local;
- búsqueda híbrida: texto libre más facetas;
- perfiles de usuario y biblioteca personal con estados y puntuaciones;
- documentación con artefactos de Diseño Dirigido por el Dominio (DDD) y de
  metodología de modelado NoSQL.

El entorno de ejecución es local: MongoDB en `mongodb://localhost:27017`,
Redis en `redis://localhost:6379` y Python 3.12 o superior. La aplicación no
depende de servicios en la nube ni de un broker de mensajes.

---

## 3. Problema y objetivos

### 3.1 Problema

Una persona que consume películas, series y anime dispersa su seguimiento en
hojas de cálculo, notas y memoria. Al mismo tiempo, las APIs públicas ofrecen
fichas completas pero no una biblioteca personal. El problema es **unificar
catálogo, descubrimiento y seguimiento personal** en una sola aplicación,
manteniendo el catálogo actualizado sin duplicar títulos.

### 3.2 Objetivo general

Diseñar e implementar una biblioteca virtual con MongoDB y Redis, aplicando
DDD para delimitar el dominio y una metodología de modelado NoSQL basada en
patrones de acceso.

### 3.3 Objetivos específicos

1. Modelar usuarios, títulos y entradas de biblioteca como agregados con
   validación e índices.
2. Implementar búsqueda híbrida con índice de texto en español y filtros por
   tipo, género, año y nota.
3. Importar títulos desde Jikan y TMDB de forma idempotente.
4. Gestionar sesiones, cache, contadores y ranking en Redis.
5. Documentar mapa de contexto, agregados, eventos, servicios y escenarios.
6. Verificar el comportamiento con pruebas automatizadas y medir el uso de
   índices y el dimensionamiento.

### 3.4 Alcance

**Incluido:** catálogo, búsqueda, ficha, registro/login, biblioteca personal,
favoritos, notas, progreso, importación, APIs JSON de lectura, cache y ranking.

**Excluido:** reproducción de video, recomendaciones con machine learning,
moderación, pagos, notificaciones push, aplicación móvil y edición colaborativa
del catálogo.

---

## 4. Marco teórico

### 4.1 Diseño Dirigido por el Dominio (DDD)

DDD propone que el software se organice alrededor del **dominio**: el problema
real del negocio, expresado en un **lenguaje ubicuo** compartido por quienes
programan y quienes conocen el negocio. Sus piezas centrales son:

- **Entidad:** objeto con identidad propia y ciclo de vida (un título, un
  usuario).
- **Objeto de valor:** inmutable y definido por sus atributos (el progreso
  `{temporada, episodio}`, una valoración de 1 a 10).
- **Agregado:** grupo de objetos que se modifican juntos y que tiene una raíz
  con identidad. Las reglas de consistencia se validan dentro del agregado.
- **Contexto delimitado (bounded context):** frontera donde un modelo y su
  lenguaje tienen un significado preciso. Un mismo término puede significar
  cosas distintas en contextos distintos.
- **Evento de dominio:** hecho relevante que ya ocurrió (`TitleImported`,
  `EntryUpdated`).
- **Servicio de dominio:** operación que no pertenece naturalmente a una
  entidad y coordina varios agregados.

En este trabajo se identifican tres contextos: **Autenticación** (soporte),
**Catálogo** (núcleo) y **Biblioteca** (núcleo). La infraestructura Redis es
un contexto genérico de apoyo, no un contexto de negocio.

### 4.2 Metodología de modelado NoSQL

A diferencia del modelado relacional, que normaliza primero y consulta después,
el modelado NoSQL parte de las **consultas** y de las **formas de acceso**. La
metodología aplicada tiene cinco pasos:

1. **Identificar entidades y relaciones** a partir del dominio.
2. **Enumerar patrones de acceso** (lecturas y escrituras) con su frecuencia y
   volumen esperado.
3. **Decidir embedding o referencia** según cardinalidad, tamaño, ciclo de vida
   y frecuencia de lectura conjunta.
4. **Definir validación e índices** para sostener las consultas y la
   integridad.
5. **Dimensionar y verificar** con `explain()`, estadísticas de colección y
   pruebas de carga o de integración.

Reglas usadas en el caso:

- Se **embebe** lo que se lee siempre junto y tiene tamaño acotado: temporadas,
  elenco, géneros, premios dentro de `titles`.
- Se **referencia** lo que tiene vida propia o cardinalidad N:M: `library_entries`
  apunta a `users` y `titles`.
- Se **desnormaliza** solo cuando el patrón de acceso lo justifica; por ejemplo,
  `year` se copia desde `release_date` para filtrar y ordenar con un índice
  entero.
- La **unicidad** se garantiza con índices únicos (`users.email`,
  `titles.external`, `library_entries.user_id + title_id`), no solo con lógica
  de aplicación.

---

## 5. Desarrollo

### 5.1 Mapa de contexto

```mermaid
flowchart LR
    U[Usuario] -->|navega, busca, guarda| WEB[Interfaz Flask/Jinja]
    WEB --> AUTH[Contexto Autenticación]
    WEB --> CAT[Contexto Catálogo]
    WEB --> LIB[Contexto Biblioteca]
    AUTH -->|sesión| REDIS[(Redis)]
    CAT -->|cache, contadores, ranking| REDIS
    CAT -->|títulos| MONGO[(MongoDB)]
    LIB -->|entradas| MONGO
    AUTH -->|usuarios| MONGO
    CAT -->|importa| EXT[APIs externas: Jikan / TMDB]
    LIB -->|consulta fichas| CAT
```

| Contexto | Tipo | Responsabilidad | Artefactos |
| --- | --- | --- | --- |
| Autenticación | Soporte | alta, login, logout, sesión | `app/auth/` |
| Catálogo | Núcleo | títulos, búsqueda, ficha, importación | `app/catalog/` |
| Biblioteca | Núcleo | estados, favoritos, notas, progreso | `app/library/` |
| Infraestructura Redis | Genérico | sesión, cache, contadores, ranking | `app/cache.py`, `app/extensions.py` |

La relación entre Catálogo y Biblioteca es **cliente-proveedor**: Biblioteca
referencia títulos por `_id` y no modifica el catálogo. Autenticación es un
contexto de soporte del que dependen los otros dos para conocer al usuario.

### 5.2 Diagrama de dominio

```mermaid
classDiagram
    class User {
      +ObjectId id
      +string email
      +string passwordHash
      +string displayName
      +Date createdAt
    }
    class Title {
      +ObjectId id
      +ExternalRef external
      +string type
      +string title
      +string synopsis
      +string[] genres
      +Date releaseDate
      +int year
      +Season[] seasons
      +string[] cast
      +string[] directors
      +double externalRating
    }
    class ExternalRef {
      +string source
      +int id
    }
    class Season {
      +int number
      +int episodes
      +Date airDate
    }
    class LibraryEntry {
      +ObjectId id
      +ObjectId userId
      +ObjectId titleId
      +string status
      +bool favorite
      +int rating
      +Progress progress
      +string notes
    }
    class Progress {
      +int season
      +int episode
    }

    User "1" --> "*" LibraryEntry : registra
    Title "1" --> "*" LibraryEntry : aparece en
    Title *-- ExternalRef
    Title *-- Season
    LibraryEntry *-- Progress
```

Decisiones visibles en el diagrama:

- `ExternalRef`, `Season` y `Progress` son **objetos de valor** embebidos.
- `LibraryEntry` es la raíz de un agregado que relaciona dos entidades.
- El estado y el favorito viven en la entrada, no en el título: son datos
  personales y cambian por usuario.

### 5.3 Agregados

#### Agregado `User`

| Elemento | Definición |
| --- | --- |
| Raíz | `User` (`_id`) |
| Invariantes | email único y con formato; contraseña con hash; nombre de 1–60 caracteres |
| Campos | `email`, `password_hash`, `display_name`, `avatar_url`, `created_at` |
| Operaciones | registrar, autenticar, consultar perfil |
| Persistencia | colección `users`, índice único `email` |

**Entradas A–D**

- **A. Datos de alta:** nombre, email, contraseña en claro (solo en tránsito).
- **B. Credenciales de login:** email y contraseña.
- **C. Contexto de sesión:** cookie `sid` y TTL configurado.
- **D. Reglas:** formato de email, largo mínimo de contraseña, nombre máximo.

**Proceso A–B**

- **A. Validación y normalización:** recortar espacios, pasar email a
  minúsculas, verificar duplicados y generar `password_hash`.
- **B. Persistencia y sesión:** insertar el documento y crear `sess:<sid>` en
  Redis con el `user_id`.

**Salidas A–H**

| Salida | Contenido |
| --- | --- |
| A | Documento en `users` |
| B | Cookie `sid` `HttpOnly` |
| C | Hash en Redis con TTL |
| D | Redirección a la página pedida (`next`) o al inicio |
| E | Mensaje de error de validación o duplicado |
| F | Contexto `g.user` disponible para las plantillas |
| G | Formulario re-renderizado ante error |
| H | Registro de alta con `created_at` |

#### Agregado `Title`

| Elemento | Definición |
| --- | --- |
| Raíz | `Title` (`_id`) |
| Invariantes | `type` en {movie, series, anime}; `external` único; `year` derivado de `release_date`; arrays válidos |
| Campos | ficha completa, temporadas embebidas, elenco, géneros, premios |
| Operaciones | importar, actualizar, buscar, ver ficha |
| Persistencia | colección `titles`, índice de texto y compuestos |

**Entradas A–D**

- **A. Payload normalizado del proveedor:** título, sinopsis, géneros, fechas,
  elenco, temporadas, póster y nota externa.
- **B. Criterios de búsqueda:** `q`, `type`, `genre`, `year_from`, `year_to`,
  `min_rating`, `sort`, `page`.
- **C. Identidad externa:** `source` e `id` para la idempotencia.
- **D. Configuración:** TTL de cache, tamaño de página, idioma del índice.

**Proceso A–B**

- **A. Normalización:** fechas a `datetime`, año derivado, temporadas a
  `{number, episodes, air_date}`, géneros y elenco a arrays.
- **B. Upsert y cache:** `update_one(upsert)` por `external.source + external.id`;
  invalidar `cache:title:*` y `cache:search:*`.

**Salidas A–H**

| Salida | Contenido |
| --- | --- |
| A | Documento en `titles` (creado o actualizado) |
| B | Ficha HTML con sinopsis, elenco, géneros, notas y temporadas |
| C | JSON de `/api/titles/<id>` |
| D | Resultados paginados de `/search` y `/api/search` |
| E | Entradas de cache en Redis |
| F | Contador de visitas y posición en `rank:popular` |
| G | Errores de proveedor o validación |
| H | `created_at` / `updated_at` para auditoría |

**Supuestos del catálogo**

- Un título pertenece a un solo tipo.
- La fecha de estreno define el año; no hay fechas parciales.
- Las temporadas se numeran desde 1 y tienen al menos un episodio.
- Las notas externas están en escala 0–10.
- El catálogo esperado es de miles de documentos, no de millones.

#### Agregado `LibraryEntry`

| Elemento | Definición |
| --- | --- |
| Raíz | `LibraryEntry` (`_id`) |
| Invariantes | una entrada por usuario y título; `status` en enum; `rating` 1–10 o nulo; `progress` con ambos campos |
| Campos | `user_id`, `title_id`, `status`, `favorite`, `rating`, `progress`, `notes` |
| Operaciones | guardar/actualizar, quitar, listar por estado, marcar favorito |
| Persistencia | colección `library_entries`, único `user_id + title_id` |

**Entradas A–D**

- **A. Estado elegido:** viendo, vista, pendiente o abandonada.
- **B. Datos personales:** favorito, nota, progreso, notas.
- **C. Identidad:** usuario de la sesión y título de la ruta.
- **D. Reglas:** rangos de nota y progreso, largo de notas, estados válidos.

**Proceso A–B**

- **A. Validación:** estado en enum; nota entera 1–10; temporada y episodio
  juntos y positivos; notas de hasta 500 caracteres.
- **B. Upsert y sincronización:** escribir la entrada y recalcular
  `cnt:likes:<title_id>` desde MongoDB; invalidar la ficha cacheada.

**Salidas A–H**

| Salida | Contenido |
| --- | --- |
| A | Documento en `library_entries` |
| B | Página “Mi biblioteca” filtrada por estado |
| C | Contadores por estado |
| D | Badge de estado en la ficha |
| E | Contador de favoritos en Redis |
| F | Promedio de notas recalculado en la ficha |
| G | Errores de validación (400) |
| H | `updated_at` y redirección a la ficha |

**Supuestos de la biblioteca**

- Un usuario tiene como máximo una entrada por título.
- El progreso solo aplica a series y anime, pero se acepta en cualquier tipo.
- El favorito es independiente del estado.
- La nota personal no modifica la nota externa del título.

#### Resumen de decisiones de embedding y referencia

| Dato | Decisión | Motivo |
| --- | --- | --- |
| Temporadas, elenco, géneros, premios | embeber en `titles` | se leen con la ficha, tamaño acotado |
| `external {source, id}` | embeber en `titles` | identidad externa del documento |
| `progress {season, episode}` | embeber en `library_entries` | objeto de valor pequeño |
| Usuario y título en la entrada | referenciar | entidades con vida propia, relación N:M |
| Contadores y ranking | Redis | datos derivados, alta escritura, bajo costo de reconstrucción |

### 5.4 Eventos de dominio

Los eventos se modelan como **hechos del lenguaje ubicuo** y se implementan
como efectos dentro de la misma transacción de solicitud; no hay broker. Esta
decisión es adecuada para el alcance y se documenta como límite.

| Evento | Disparador | Consumidor / efecto |
| --- | --- | --- |
| `UserRegistered` | alta exitosa | crear sesión Redis, redirigir |
| `UserLoggedIn` | credenciales válidas | crear sesión Redis |
| `UserLoggedOut` | logout | borrar `sess:<sid>` y cookie |
| `TitleImported` | importación desde API | invalidar cache de fichas y búsquedas |
| `TitleViewed` | `GET /titles/<id>` | `INCR cnt:views` y `ZINCRBY rank:popular` |
| `EntrySaved` | alta/edición de biblioteca | sincronizar `cnt:likes`, invalidar ficha |
| `EntryDeleted` | borrado de biblioteca | recalcular `cnt:likes`, invalidar ficha |
| `RatingChanged` | nota personal guardada | promedio recalculado en la próxima lectura |

### 5.5 Servicios de dominio

| Servicio | Responsabilidad | Implementación |
| --- | --- | --- |
| Autenticación | validar credenciales, crear/destruir sesión | `app/auth/routes.py`, `app/auth/session.py` |
| Búsqueda de catálogo | interpretar filtros, construir consulta, paginar | `app/catalog/services.py` |
| Importación | consultar proveedor, normalizar, upsert idempotente | `app/catalog/providers.py`, `app/catalog/importer.py` |
| Biblioteca | validar y persistir entradas, listar por estado | `app/library/services.py` |
| Cache y ranking | cache-aside, contadores, sorted set | `app/cache.py` |
| Promedio de notas | agregación sobre `library_entries` | `average_rating()` en `app/catalog/services.py` |

Los servicios no conocen HTTP: reciben documentos o diccionarios y devuelven
documentos o resultados. Las rutas se ocupan de la sesión, la validación de
formularios y la respuesta HTML/JSON.

### 5.6 Diagramas de escenario

#### Escenario 1 — Búsqueda híbrida

```mermaid
sequenceDiagram
    actor U as Usuario
    participant F as Flask (/search)
    participant R as Redis
    participant M as MongoDB
    U->>F: q=nolan&type=movie&sort=relevance
    F->>R: GET cache:search:catalogo:<hash>
    alt cache hit
        R-->>F: resultados serializados
    else cache miss
        F->>M: find({$text, type}).sort(textScore)
        M-->>F: documentos + total
        F->>R: SET cache:search... EX 60
    end
    F-->>U: HTML con tarjetas y paginación
```

#### Escenario 2 — Importación desde API

```mermaid
sequenceDiagram
    actor U as Usuario autenticado
    participant F as Flask (/import)
    participant P as Proveedor (Jikan/TMDB)
    participant M as MongoDB
    participant R as Redis
    U->>F: GET /import?q=attack&source=jikan
    F->>P: búsqueda
    P-->>F: resultados normalizados
    F-->>U: lista para importar
    U->>F: POST /import (source, external_id)
    F->>P: detalle del título
    P-->>F: payload normalizado
    F->>M: update_one(upsert) por external
    F->>R: DEL cache:title:* y cache:search:*
    F-->>U: redirección a la ficha
```

#### Escenario 3 — Guardar en la biblioteca

```mermaid
sequenceDiagram
    actor U as Usuario
    participant F as Flask (/library/<id>)
    participant M as MongoDB
    participant R as Redis
    U->>F: POST status=watching&rating=9&favorite=on
    F->>F: validar estado, nota y progreso
    alt inválido
        F-->>U: 400 con el formulario y el error
    else válido
        F->>M: update_one(upsert) user_id + title_id
        F->>M: count_documents(favorite=true)
        F->>R: SET cnt:likes:<id>
        F->>R: DEL cache:title:*
        F-->>U: 302 a /titles/<id>#library
    end
```

#### Escenario 4 — Visita a una ficha

```mermaid
sequenceDiagram
    actor U as Usuario
    participant F as Flask (/titles/<id>)
    participant M as MongoDB
    participant R as Redis
    U->>F: GET /titles/<id>
    F->>M: find_one(_id)
    M-->>F: documento
    F->>R: INCR cnt:views:<id>
    F->>R: ZINCRBY rank:popular 1 <id>
    F->>M: aggregate promedio de notas
    M-->>F: {average, count}
    F-->>U: HTML de la ficha
```

---

## 6. Implementación

### 6.1 Arquitectura

La aplicación usa el patrón **application factory** de Flask. `create_app()`
carga configuración, registra los blueprints `auth`, `catalog` y `library`,
inyecta el usuario de la sesión en `g` y expone `/health`.

```text
caso de estudio 2/
├─ app/
│  ├─ __init__.py          # factory, blueprints, contexto de usuario
│  ├─ config.py            # .env, Mongo, Redis, APIs
│  ├─ extensions.py        # clientes Mongo y Redis por aplicación
│  ├─ cache.py             # claves, cache-aside, contadores, ranking
│  ├─ run.py               # punto de entrada
│  ├─ auth/                # registro, login, logout, sesión Redis
│  ├─ catalog/             # búsqueda, ficha, APIs, proveedores, importador
│  ├─ library/             # estados, favoritos, notas, progreso
│  ├─ templates/           # Jinja: base, index, search, detail, import, library
│  └─ static/css/style.css
├─ mongodb/
│  ├─ init/                # validadores JSON Schema e índices
│  ├─ seed/                # dataset y cargadores
│  ├─ aggregations/        # reportes del informe
│  └─ queries/             # explain y dimensionamiento
├─ redis/
│  └─ README.md            # mapa de claves y operación
├─ tests/                  # 70 pruebas automatizadas
└─ docs/
   └─ informe.md           # este documento
```

### 6.2 Rutas

| Método | Ruta | Descripción | Auth |
| --- | --- | --- | --- |
| GET | `/` | inicio: tendencias, mejores notas, recientes | no |
| GET | `/search` | búsqueda híbrida paginada | no |
| GET | `/titles/<id>` | ficha con elenco, temporadas y promedio | no |
| GET | `/api/search` | búsqueda en JSON | no |
| GET | `/api/titles/<id>` | ficha en JSON con promedio | no |
| GET | `/import` | buscador de APIs externas | sí |
| POST | `/import` | importa y redirige a la ficha | sí |
| GET | `/auth/register` | formulario de alta | no |
| POST | `/auth/register` | crea usuario y sesión | no |
| GET | `/auth/login` | formulario de login | no |
| POST | `/auth/login` | valida y crea sesión | no |
| POST | `/auth/logout` | destruye la sesión | no |
| GET | `/library` | biblioteca personal filtrable | sí |
| POST | `/library/<id>` | alta o edición de entrada | sí |
| POST | `/library/<id>/delete` | quita la entrada | sí |
| GET | `/health` | chequeo de salud | no |

### 6.3 Búsqueda híbrida

`parse_filters()` normaliza los parámetros y `build_filter()` construye el
documento de consulta. Si hay texto, se usa `$text` con el índice
`text_busqueda`; el orden por defecto es `$meta: textScore`. Los filtros de
tipo, género, año y nota se combinan con AND. La paginación es fija en 12
resultados.

Pesos del índice de texto: título 10, título original 8, sinopsis 3, elenco 2,
dirección 2, estudios 2, géneros 1. El índice usa `default_language: "spanish"`
para que el stemming funcione en español (`correr` encuentra `corriendo`).

### 6.4 Importación idempotente

Los proveedores devuelven un **payload normalizado** común. El importador
convierte fechas, deriva el año, normaliza temporadas y hace
`update_one(upsert)` por `external.source + external.id`, preservando
`created_at` con `$setOnInsert`. Si el título ya existe, se actualiza en lugar
de duplicarse.

TMDB requiere `TMDB_API_KEY`; Jikan no requiere clave. El entorno de
desarrollo usado para este informe no tuvo salida a internet, por lo que la
importación se verificó con payloads grabados en las pruebas y el comando
`python -m mongodb.seed.import_external` quedó listo para ejecutarse con red.

### 6.5 Redis: sesión, cache, contadores y ranking

El detalle del mapa de claves está en `redis/README.md`. Resumen:

- `sess:<sid>` — hash con `user_id`, TTL de 7 días.
- `cache:search:<db>:<hash>` — resultados serializados, TTL 60 s.
- `cache:title:<db>:<id>` — ficha + promedio, TTL 300 s.
- `cnt:views:<id>` y `cnt:likes:<id>` — contadores enteros.
- `rank:popular` — sorted set de visitas por título.

La invalidación es explícita al importar y al modificar la biblioteca; las
búsquedas además expiran por TTL. El cliente usa `protocol=2` porque el build
5.0.14.1 de Redis para Windows no soporta `HELLO 3`.

### 6.6 Validación e índices

Los validadores JSON Schema de `mongodb/init/01_collections.js` exigen los
campos obligatorios, tipos y enums, y usan `additionalProperties: false` en
`titles` y `library_entries`. Esto obliga a declarar cada campo nuevo y evita
documentos con forma irregular.

Los índices de `mongodb/init/02_indexes.js` cubren texto, facetas, orden,
unicidad y búsquedas por usuario. El índice de texto se recrea con
`dropIndex` para fijar el idioma español, porque `createIndex` no modifica las
opciones de un índice existente.

### 6.7 Pruebas

La suite usa `pytest` y crea bases `catalogo_test_*` y la base 15 de Redis por
fixture. Cubre:

- salud de la aplicación y conexión a Mongo/Redis;
- sesiones Redis (creación, lectura, expiración, destrucción);
- registro, login, logout y redirección con `next`;
- búsqueda por texto, filtros, orden, paginación y promedio;
- rutas HTML y APIs JSON;
- proveedores, importador y rutas de importación;
- biblioteca: alta, edición, borrado, validación y filtros;
- cache, contadores, ranking e invalidación;
- agregaciones, `explain()` y dimensionamiento.

```powershell
python -m pytest -q
```

---

## 7. Análisis de resultados

### 7.1 Catálogo y seed

El seed inicial tiene 16 títulos:

| Tipo | Cantidad |
| --- | --- |
| Películas | 4 |
| Series | 5 |
| Anime | 7 |
| **Total** | **16** |

La distribución permite ejercitar las tres ramas del polimorfismo y las
facetas de tipo. La importación permite ampliar el catálogo sin cambiar el
modelo.

### 7.2 Planes de ejecución

Salida de `mongodb/queries/report_queries.js` sobre el catálogo local:

| Consulta | Etapa | nReturned | Claves examinadas | Documentos examinados | ms |
| --- | --- | --- | --- | --- | --- |
| `texto_libre` (`drama`) | `TEXT_MATCH` | 10 | 10 | 10 | 3 |
| `filtro_tipo_anio` (series desde 2010) | `FETCH <- IXSCAN` | 3 | 3 | 3 | 1 |
| `genero_tipo` (anime + Acción) | `FETCH <- IXSCAN` | 4 | 4 | 4 | 1 |
| `biblioteca_usuario` | `FETCH <- IXSCAN` | 0 | 0 | 0 | 1 |
| `favoritos_usuario` | `FETCH <- IXSCAN` | 0 | 0 | 0 | 1 |

Lectura: en todas las consultas `nReturned == totalKeysExamined ==
totalDocsExamined`. No hay exámenes de documentos de más ni colecciones
recorridas completas (`COLLSCAN`). La consulta de texto usa el índice invertido
y las demás usan índices compuestos o parciales.

### 7.3 Dimensionamiento

Salida de `mongodb/queries/sizing.js`:

| Colección | Documentos | Tamaño medio | Almacenamiento | Índices | Tamaño de índices |
| --- | --- | --- | --- | --- | --- |
| `titles` | 16 | 736 B | 24 KB | 7 | 144 KB |
| `library_entries` | 0 | — | 4 KB | 5 | 20 KB |
| `users` | 0 | — | 4 KB | 2 | 8 KB |

Los índices ocupan más que los datos porque el catálogo es mínimo. Con el
crecimiento esperado (miles de títulos), la proporción se estabiliza y el
costo dominante pasa a ser el índice de texto. El dimensionamiento se incluye
como método reproducible, no como conclusión sobre un volumen grande.

### 7.4 Cache y ranking

- La búsqueda repetida con los mismos filtros se resuelve desde Redis sin
  tocar MongoDB (`cache:search`).
- La ficha JSON se cachea 5 minutos (`cache:title`); se invalida al importar o
  al cambiar la biblioteca.
- Cada visita a una ficha incrementa `cnt:views` y `rank:popular`; la home
  muestra “Tendencias” a partir de ese sorted set.
- `cnt:likes` se recalcula desde MongoDB en cada cambio de entrada, lo que
  evita desviaciones por escrituras concurrentes o borrados.

### 7.5 Pruebas y calidad

La suite completa pasa con **70 pruebas**. Los fallos corregidos durante el
desarrollo quedaron cubiertos por pruebas de regresión:

- el índice de texto no aplicaba stemming en español hasta fijar
  `default_language`;
- los validadores rechazaban `_id` hasta declararlo en `additionalProperties`;
- redis-py 8 fallaba con `HELLO` hasta fijar RESP2;
- el detalle no serializaba `air_date` de las temporadas hasta normalizarlo;
- el login no respetaba `next` hasta agregar el parámetro a la ruta y al
  formulario.

### 7.6 Límites y trabajo futuro

- **Sin salida a internet en el entorno de prueba:** la importación en vivo
  quedó preparada y probada con payloads; falta ejecutarla contra las APIs
  reales.
- **Sin broker de eventos:** los eventos son efectos sincrónicos; una cola
  permitiría desacoplar contadores y notificaciones.
- **Cache con invalidación por prefijo:** usa `SCAN`; en una instancia grande
  convendría versionar claves o usar tags.
- **Búsqueda:** no hay tolerancia a errores ortográficos ni sinónimos; se
  podría evaluar Atlas Search o un índice adicional.
- **Recomendaciones:** el modelo actual permitiría calcularlas con agregaciones
  sobre `library_entries`, pero quedan fuera del alcance.
- **Seguridad:** faltan límite de intentos de login, verificación de email y
  rotación de sesión.

---

## 8. Conclusiones

El caso permitió aplicar DDD y modelado NoSQL en un dominio acotado pero
completo. Las decisiones principales fueron:

1. **Separar contextos** (Autenticación, Catálogo, Biblioteca) evitó mezclar
   datos personales con datos del catálogo y dejó claro qué agregado posee cada
   invariante.
2. **Embeber lo que se lee junto y referenciar lo que tiene vida propia**
   produjo un modelo simple: tres colecciones, sin duplicar fichas por usuario.
3. **Modelar desde las consultas** justificó los índices compuestos, el índice
   de texto en español y el índice parcial de favoritos. Los planes de
   ejecución confirman que las consultas usan índices y examinan solo lo
   necesario.
4. **Redis no reemplaza a MongoDB**: se usó para lo que hace bien (sesión,
   cache, contadores, ranking) y MongoDB siguió siendo la fuente de verdad.
5. **La idempotencia** por identidad externa y la unicidad por índices
   evitaron duplicados sin depender solo de la lógica de la aplicación.
6. **Las pruebas automatizadas** fueron el mecanismo para descubrir y fijar
   decisiones delicadas (idioma del índice, RESP2, validadores, `next`).

Como aprendizaje, el modelado NoSQL exige explicitar supuestos y patrones de
acceso; cuando eso se hace, el esquema resultante es más pequeño y predecible
que una traducción directa del modelo relacional.

---

## 9. Bibliografía

- Evans, E. (2003). *Domain-Driven Design: Tackling Complexity in the Heart of
  Software*. Addison-Wesley.
- Vernon, V. (2013). *Implementing Domain-Driven Design*. Addison-Wesley.
- Fowler, M. (2015). *Microservices Patterns* / artículos sobre bounded context
  y agregados. https://martinfowler.com
- MongoDB. *Data Modeling Guide*.
  https://www.mongodb.com/docs/manual/data-modeling/
- MongoDB. *Text Indexes*.
  https://www.mongodb.com/docs/manual/core/index-text/
- MongoDB. *JSON Schema Validation*.
  https://www.mongodb.com/docs/manual/core/schema-validation/
- MongoDB. *Aggregation Pipeline*.
  https://www.mongodb.com/docs/manual/core-aggregation-pipeline/
- Redis. *Data types* y *EXPIRE*.
  https://redis.io/docs/latest/develop/data-types/
- Redis. *Sorted sets*.
  https://redis.io/docs/latest/develop/data-types/sorted-sets/
- Pallets Projects. *Flask Documentation*.
  https://flask.palletsprojects.com/
- PyMongo. *Documentation*.
  https://pymongo.readthedocs.io/
- redis-py. *Documentation*.
  https://redis-py.readthedocs.io/
- Jikan. *Jikan API v4*.
  https://docs.api.jikan.moe/
- TMDB. *API Documentation*.
  https://developer.themoviedb.org/docs
