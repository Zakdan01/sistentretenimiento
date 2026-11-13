// Salud del catálogo: volumen, valoración media y episodios por tipo.
// Uso: mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/aggregations/03_catalog_health.js
const pipeline = [
  {
    $group: {
      _id: "$type",
      titles: { $sum: 1 },
      avg_external_rating: { $avg: "$external_rating" },
      avg_year: { $avg: "$year" },
      episodes: { $sum: { $ifNull: ["$episodes_total", 0] } },
    },
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      type: "$_id",
      titles: 1,
      avg_external_rating: { $round: ["$avg_external_rating", 2] },
      avg_year: { $round: ["$avg_year", 0] },
      episodes: 1,
    },
  },
];

print(JSON.stringify(db.titles.aggregate(pipeline).toArray()));
