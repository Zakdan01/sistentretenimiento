// Usuarios más activos: cantidad de entradas, favoritos y nota media.
// Uso: mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/aggregations/04_user_activity.js
const pipeline = [
  {
    $group: {
      _id: "$user_id",
      entries: { $sum: 1 },
      favorites: { $sum: { $cond: ["$favorite", 1, 0] } },
      avg_rating: { $avg: "$rating" },
    },
  },
  {
    $lookup: {
      from: "users",
      localField: "_id",
      foreignField: "_id",
      as: "user",
    },
  },
  { $unwind: "$user" },
  {
    $project: {
      _id: 0,
      user: "$user.display_name",
      entries: 1,
      favorites: 1,
      avg_rating: { $round: ["$avg_rating", 2] },
    },
  },
  { $sort: { entries: -1, user: 1 } },
];

print(JSON.stringify(db.library_entries.aggregate(pipeline).toArray()));
