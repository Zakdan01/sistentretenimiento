// Elimina la colección polimórfica `titles` de la versión anterior.
// Ejecutar SOLO cuando la aplicación ya usa movies/series/animes y la suite pasa.
// Uso: mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/init/03_drop_legacy.js

if (db.getCollectionNames().includes("titles")) {
  db.titles.drop();
  print("eliminada: titles");
} else {
  print("titles no existe; nada que eliminar");
}
