"""Genera `data/libraries.json` a partir del catálogo ya descargado.

Las bibliotecas demo referencian títulos por `source + external_id`, nunca por
`_id`, para que el seed funcione en cualquier base. El resultado es
determinístico: siempre elige los mismos títulos de los snapshots.

Uso:
    python -m mongodb.seed.build_demo
"""

from __future__ import annotations

import json
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent
DATA_DIR = SEED_DIR / "data"
OUTPUT = DATA_DIR / "libraries.json"

CATALOG_FILES = {
    "movie": "movies.json",
    "series": "series.json",
    "anime": "animes.json",
}

# (email, [(tipo, posición en el snapshot, estado, favorito, nota, progreso, notas)])
PLANS = {
    "laura@biblioteca.local": [
        ("movie", 0, "watched", True, 9, None, "La vi dos veces; el montaje es impecable."),
        ("series", 0, "watching", True, 9, {"season": 2, "episode": 5}, "Engancha desde el primer capítulo."),
        ("anime", 0, "watched", True, 10, None, "Una de mis favoritas de todos los tiempos."),
        ("movie", 1, "planned", False, None, None, "Me la recomendaron para el fin de semana."),
        ("series", 1, "planned", False, None, None, None),
        ("anime", 1, "dropped", False, 5, None, "No me convenció el ritmo."),
        ("series", 2, "dropped", False, None, None, None),
        ("anime", 2, "watching", False, 8, {"season": 1, "episode": 3}, None),
        ("movie", 2, "watched", False, 8, None, None),
        ("series", 3, "watched", False, 7, None, "Buena, aunque decae en la última temporada."),
    ],
    "diego@biblioteca.local": [
        ("anime", 3, "watching", True, 9, {"season": 3, "episode": 10}, "La animación es espectacular."),
        ("movie", 3, "watched", False, 8, None, None),
        ("series", 4, "watched", True, 9, None, "Final redondo."),
        ("anime", 4, "planned", False, None, None, "La tengo pendiente para vacaciones."),
        ("movie", 4, "planned", False, None, None, None),
        ("series", 5, "dropped", False, None, None, "La dejé en la primera temporada."),
        ("anime", 5, "dropped", False, 6, None, None),
        ("movie", 5, "watching", False, None, None, "La empecé anoche."),
    ],
}


def main() -> None:
    catalog = {
        title_type: json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
        for title_type, filename in CATALOG_FILES.items()
    }

    libraries: dict[str, list[dict]] = {}
    for email, rows in PLANS.items():
        entries = []
        for title_type, position, status, favorite, rating, progress, notes in rows:
            title = catalog[title_type][position]
            entries.append(
                {
                    "source": title["source"],
                    "external_id": title["external_id"],
                    "status": status,
                    "favorite": favorite,
                    "rating": rating,
                    "progress": progress,
                    "notes": notes,
                }
            )
        libraries[email] = entries

    OUTPUT.write_text(
        json.dumps(libraries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    total = sum(len(entries) for entries in libraries.values())
    print(f"escrito {OUTPUT.name}: {len(libraries)} usuarios, {total} entradas")


if __name__ == "__main__":
    main()
