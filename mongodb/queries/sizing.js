// Tamaño y uso de disco por colección, para la sección de dimensionamiento.
// Uso: mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/queries/sizing.js
const report = db
  .getCollectionNames()
  .sort()
  .map((name) => {
    const stats = db.getCollection(name).stats();
    return {
      collection: name,
      documents: stats.count,
      avgObjectSize: Math.round(stats.avgObjSize || 0),
      storageSize: stats.storageSize,
      totalIndexSize: stats.totalIndexSize,
      indexes: stats.nindexes,
    };
  });

print(JSON.stringify(report));
