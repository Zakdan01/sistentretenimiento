// Inicializa las colecciones y sus validadores.
// Uso: mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/01_collections.js

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

const catalogProperties = {
  _id: { bsonType: "objectId" },
  external: {
    bsonType: ["object", "null"],
    required: ["source", "id"],
    properties: {
      source: { enum: ["imdb", "tmdb", "jikan", "anilist", "manual"] },
      id: { bsonType: ["int", "long", "string"] },
    },
    additionalProperties: false,
  },
  type: { enum: ["movie", "series", "anime"] },
  title: { bsonType: "string", minLength: 1 },
  poster_url: { bsonType: ["string", "null"] },
  synopsis: { bsonType: "string" },
  year: { bsonType: ["int", "null"], minimum: 1900, maximum: 2100 },
  genres: { bsonType: "array", items: { bsonType: "string" } },
  external_rating: { bsonType: ["double", "int", "null"] },
  created_at: { bsonType: "date" },
  updated_at: { bsonType: "date" },
};

function catalogValidator(type) {
  return {
    $jsonSchema: {
      bsonType: "object",
      required: ["type", "title", "synopsis", "genres", "year", "created_at", "updated_at"],
      properties: {
        ...catalogProperties,
        // Cada colección guarda un solo tipo; así se evita mezclar películas en `series`.
        type: { enum: [type] },
      },
      additionalProperties: false,
    },
  };
}

ensureCollection("movies", catalogValidator("movie"));
ensureCollection("series", catalogValidator("series"));
ensureCollection("animes", catalogValidator("anime"));

ensureCollection("users", {
  $jsonSchema: {
    bsonType: "object",
    required: ["email", "password_hash", "display_name", "role", "created_at"],
    properties: {
      _id: { bsonType: "objectId" },
      email: { bsonType: "string", pattern: "^[^@]+@[^@]+\\.[^@]+$" },
      password_hash: { bsonType: "string" },
      display_name: { bsonType: "string", minLength: 1, maxLength: 60 },
      role: { enum: ["admin", "user"] },
      avatar_url: { bsonType: ["string", "null"] },
      created_at: { bsonType: "date" },
    },
    additionalProperties: false,
  },
});

ensureCollection("library_entries", {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "user_id",
      "title_id",
      "title_type",
      "status",
      "favorite",
      "created_at",
      "updated_at",
    ],
    properties: {
      _id: { bsonType: "objectId" },
      user_id: { bsonType: "objectId" },
      title_id: { bsonType: "objectId" },
      title_type: { enum: ["movie", "series", "anime"] },
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
