// Géneros más presentes y valoración media de sus títulos (5 colecciones).
// Uso: mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/aggregations/01_top_genres.js
const pipeline = [
  { $unionWith: "series" },
  { $unionWith: "animes" },
  { $unwind: "$genres" },
  {
    $group: {
      _id: "$genres",
      titles: { $sum: 1 },
      avg_rating: { $avg: "$external_rating" },
    },
  },
  { $sort: { titles: -1, _id: 1 } },
  {
    $project: {
      _id: 0,
      genre: "$_id",
      titles: 1,
      avg_rating: { $round: ["$avg_rating", 2] },
    },
  },
];

print(JSON.stringify(db.movies.aggregate(pipeline).toArray()));
