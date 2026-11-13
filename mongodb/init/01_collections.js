// Inicializa las colecciones y sus validadores.
// Uso: mongosh "mongodb://localhost:27017/catalogo" mongodb/init/01_collections.js

function ensureCollection(name, validator) {
  const options = {
    validator,
    validationLevel: "strict",
    validationAction: "error",
  };

  if (db.getCollectionNames().includes(name)) {
    db.runCommand({ collMod: name, ...options });
    print(`actualizada: ${name}`);
  } else {
    db.createCollection(name, options);
    print(`creada: ${name}`);
  }
}

ensureCollection("users", {
  $jsonSchema: {
    bsonType: "object",
    required: ["email", "password_hash", "display_name", "created_at"],
    properties: {
      _id: { bsonType: "objectId" },
      email: { bsonType: "string", pattern: "^[^@]+@[^@]+\\.[^@]+$" },
      password_hash: { bsonType: "string" },
      display_name: { bsonType: "string", minLength: 1, maxLength: 60 },
      avatar_url: { bsonType: ["string", "null"] },
      created_at: { bsonType: "date" },
    },
    additionalProperties: true,
  },
});

ensureCollection("titles", {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "external",
      "type",
      "title",
      "synopsis",
      "genres",
      "release_date",
      "year",
      "created_at",
      "updated_at",
    ],
    properties: {
      _id: { bsonType: "objectId" },
      external: {
        bsonType: "object",
        required: ["source", "id"],
        properties: {
          source: { enum: ["tmdb", "jikan"] },
          id: { bsonType: "int" },
        },
        additionalProperties: false,
      },
      type: { enum: ["movie", "series", "anime"] },
      title: { bsonType: "string", minLength: 1 },
      original_title: { bsonType: "string" },
      synopsis: { bsonType: "string" },
      genres: {
        bsonType: "array",
        items: { bsonType: "string" },
      },
      release_date: { bsonType: "date" },
      year: { bsonType: "int", minimum: 1900, maximum: 2100 },
      runtime_minutes: { bsonType: ["int", "null"], minimum: 1 },
      seasons: {
        bsonType: "array",
        items: {
          bsonType: "object",
          required: ["number", "episodes"],
          properties: {
            number: { bsonType: "int", minimum: 1 },
            episodes: { bsonType: "int", minimum: 1 },
            air_date: { bsonType: "date" },
          },
          additionalProperties: false,
        },
      },
      episodes_total: { bsonType: ["int", "null"], minimum: 1 },
      directors: { bsonType: "array", items: { bsonType: "string" } },
      cast: { bsonType: "array", items: { bsonType: "string" } },
      studios: { bsonType: "array", items: { bsonType: "string" } },
      poster_url: { bsonType: ["string", "null"] },
      external_rating: { bsonType: ["double", "int", "null"] },
      awards: { bsonType: "array", items: { bsonType: "string" } },
      created_at: { bsonType: "date" },
      updated_at: { bsonType: "date" },
    },
    additionalProperties: false,
  },
});

ensureCollection("library_entries", {
  $jsonSchema: {
    bsonType: "object",
    required: ["user_id", "title_id", "status", "favorite", "created_at", "updated_at"],
    properties: {
      _id: { bsonType: "objectId" },
      user_id: { bsonType: "objectId" },
      title_id: { bsonType: "objectId" },
      status: { enum: ["watching", "watched", "planned", "dropped"] },
      favorite: { bsonType: "bool" },
      rating: { bsonType: ["int", "null"], minimum: 1, maximum: 10 },
      progress: {
        bsonType: ["object", "null"],
        required: ["season", "episode"],
        properties: {
          season: { bsonType: "int", minimum: 1 },
          episode: { bsonType: "int", minimum: 1 },
        },
        additionalProperties: false,
      },
      notes: { bsonType: ["string", "null"] },
      created_at: { bsonType: "date" },
      updated_at: { bsonType: "date" },
    },
    additionalProperties: false,
  },
});

print("colecciones listas");
