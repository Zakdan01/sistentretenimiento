// Crea los índices del sistema. Es idempotente.
// Uso: mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/02_indexes.js

const CATALOG_COLLECTIONS = ["movies", "series", "animes"];

for (const name of CATALOG_COLLECTIONS) {
  const collection = db.getCollection(name);

  // Búsqueda híbrida: texto libre con pesos por relevancia.
  // Se recrea para fijar el idioma: createIndex no cambia opciones existentes.
  try {
    collection.dropIndex("text_busqueda");
  } catch (error) {
    // el índice todavía no existía
  }

  collection.createIndex(
    { title: "text", synopsis: "text", genres: "text" },
    {
      name: "text_busqueda",
      default_language: "spanish",
      weights: { title: 10, synopsis: 3, genres: 1 },
    }
  );

  collection.createIndex({ year: -1 }, { name: "anio" });
  collection.createIndex({ genres: 1, year: -1 }, { name: "genero_anio" });
  collection.createIndex({ external_rating: -1 }, { name: "valoracion_externa" });

  // Evita duplicar el mismo título de la misma fuente. Los títulos manuales
  // (`external: null`) quedan fuera del índice parcial.
  collection.createIndex(
    { "external.source": 1, "external.id": 1 },
    {
      name: "uq_fuente_externa",
      unique: true,
      partialFilterExpression: { external: { $type: "object" } },
    }
  );
}

db.users.createIndex({ email: 1 }, { name: "uq_email", unique: true });
db.users.createIndex({ role: 1 }, { name: "rol" });

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
db.library_entries.createIndex({ title_type: 1 }, { name: "tipo_titulo" });

print("índices listos");
