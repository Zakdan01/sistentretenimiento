// Top 3 títulos mejor valorados por tipo, usando funciones de ventana.
// Uso: mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/aggregations/05_top_rated_by_type.js
const pipeline = [
  { $unionWith: "series" },
  { $unionWith: "animes" },
  {
    $setWindowFields: {
      partitionBy: "$type",
      sortBy: { external_rating: -1 },
      output: { position: { $rank: {} } },
    },
  },
  { $match: { position: { $lte: 3 } } },
  {
    $project: {
      _id: 0,
      type: 1,
      title: 1,
      external_rating: 1,
      position: 1,
    },
  },
  { $sort: { type: 1, position: 1 } },
];

print(JSON.stringify(db.movies.aggregate(pipeline).toArray()));
