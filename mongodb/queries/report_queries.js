// Planes de ejecución de las consultas del informe.
// Uso: mongosh "mongodb://localhost:27017/catalogo" --quiet --file mongodb/queries/report_queries.js
function summarize(label, explain) {
  const stats = explain.executionStats || {};
  const winning = explain.queryPlanner.winningPlan;
  const stage =
    winning.stage === "FETCH" && winning.inputStage
      ? `${winning.stage} <- ${winning.inputStage.stage}`
      : winning.stage;

  print(
    JSON.stringify({
      query: label,
      stage,
      nReturned: stats.nReturned,
      totalKeysExamined: stats.totalKeysExamined,
      totalDocsExamined: stats.totalDocsExamined,
      executionTimeMillis: stats.executionTimeMillis,
    })
  );
}

summarize(
  "texto_libre",
  db.movies.find({ $text: { $search: "drama" } }).explain("executionStats")
);

summarize(
  "filtro_anio",
  db.series
    .find({ year: { $gte: 2010 } })
    .sort({ year: -1 })
    .explain("executionStats")
);

summarize(
  "genero",
  db.animes
    .find({ genres: "Acción" })
    .explain("executionStats")
);

summarize(
  "biblioteca_usuario",
  db.library_entries
    .find({ user_id: ObjectId(), status: "watching" })
    .explain("executionStats")
);

summarize(
  "favoritos_usuario",
  db.library_entries
    .find({ user_id: ObjectId(), favorite: true })
    .explain("executionStats")
);
