// Crea los índices del sistema. Es idempotente.
// Uso: mongosh "mongodb://localhost:27017/catalogo" mongodb/init/02_indexes.js

// Búsqueda híbrida: texto libre con pesos por relevancia.
// Se recrea para fijar el idioma: createIndex no cambia opciones existentes.
try {
  db.titles.dropIndex("text_busqueda");
} catch (error) {
  // el índice todavía no existía
}

db.titles.createIndex(
  {
    title: "text",
    original_title: "text",
    synopsis: "text",
    cast: "text",
    directors: "text",
    studios: "text",
    genres: "text",
  },
  {
    name: "text_busqueda",
    default_language: "spanish",
    weights: {
      title: 10,
      original_title: 8,
      synopsis: 3,
      cast: 2,
      directors: 2,
      studios: 2,
      genres: 1,
    },
  }
);

// Filtros y ordenamientos del catálogo.
db.titles.createIndex({ type: 1, year: -1 }, { name: "tipo_anio" });
db.titles.createIndex({ type: 1, genres: 1 }, { name: "tipo_genero" });
db.titles.createIndex({ year: -1 }, { name: "anio" });
db.titles.createIndex({ external_rating: -1 }, { name: "valoracion_externa" });

// Evita importar dos veces el mismo título desde la misma fuente.
db.titles.createIndex(
  { "external.source": 1, "external.id": 1 },
  { name: "uq_fuente_externa", unique: true }
);

db.users.createIndex({ email: 1 }, { name: "uq_email", unique: true });

// Un solo estado por usuario y título.
db.library_entries.createIndex(
  { user_id: 1, title_id: 1 },
  { name: "uq_usuario_titulo", unique: true }
);
db.library_entries.createIndex(
  { user_id: 1, status: 1, updated_at: -1 },
  { name: "usuario_estado" }
);
db.library_entries.createIndex({ title_id: 1, status: 1 }, { name: "titulo_estado" });
db.library_entries.createIndex(
  { user_id: 1 },
  { name: "usuario_favoritos", partialFilterExpression: { favorite: true } }
);

print("índices listos");
