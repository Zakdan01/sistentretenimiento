// Actividad por usuario: entradas de biblioteca agrupadas por estado.
// Uso: mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/aggregations/02_library_by_status.js
const pipeline = [
  {
    $group: {
      _id: { user: "$user_id", status: "$status" },
      total: { $sum: 1 },
    },
  },
  {
    $group: {
      _id: "$_id.user",
      total: { $sum: "$total" },
      statuses: {
        $push: { status: "$_id.status", total: "$total" },
      },
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
      total: 1,
      statuses: 1,
    },
  },
  { $sort: { total: -1, user: 1 } },
];

print(JSON.stringify(db.library_entries.aggregate(pipeline).toArray()));
