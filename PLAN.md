# Plan de ejecución — catálogo en 5 colecciones

Rama: `feat/catalogo-5-colecciones`. Datos: 500 títulos por tipo (películas,
series, anime) desde Wikipedia ES/EN, Wikidata e IMDb; 1 admin + 2 usuarios
comunes con bibliotecas de ejemplo; panel de administración CRUD.

## Ledger

- [x] 0. Calibrar pipeline de datos (rendimiento y cobertura de imágenes).
- [ ] 1. Generar `mongodb/seed/data/{movies,series,animes}.json` (500 c/u).
- [x] 2. Migrar `app/catalog` (services, routes, importer, providers) a
      `movies`/`series`/`animes`.
- [x] 3. Migrar `app/library` a `title_type` + resolución por colección.
- [x] 4. Rol `user` al registrar + blueprint `admin` (dashboard, CRUD de
      títulos y usuarios, reportes).
- [x] 5. Seed limpio: loaders separados de JSON, usuarios demo y bibliotecas.
- [x] 6. Reescribir agregaciones, consultas y `sizing.js` para 5 colecciones.
- [x] 7. Reescribir la suite de pruebas (init, seed, catálogo, biblioteca,
      admin, reportes, proveedores, importación, cache): 121 pruebas en verde.
- [ ] 8. Actualizar `docs/informe.md` (secciones 7 con datos reales),
      `mongodb/README.md`, `redis/README.md`, `README.md`, `AGENTS.md`.
- [ ] 9. Verificación final: `pytest -q` completo + smoke de la app.

## Decisiones fijas

- Colecciones: `users`, `movies`, `series`, `animes`, `library_entries` en la
  base `catalogo`. Nada de `titles` ni bases paralelas.
- Documento de catálogo: `_id`, `external`, `type`, `title`, `poster_url`,
  `synopsis`, `year`, `genres`, `external_rating`, `created_at`, `updated_at`.
- JSON de catálogo: `source`, `external_id`, `title`, `image`, `synopsis`,
  `year`, `genres`, `rating` (solo lo necesario).
- Identidad idempotente: `external.source + external.id`; títulos manuales con
  `external: null`.
- `library_entries.title_type` obligatorio para resolver el `$lookup`.
- Cache Redis namespaceado por base (`cache:*:<db>:*`), TTL 60/300/600.
- Sin `mongodump`: respaldo opcional con `$out` a `catalogo_backup`.
