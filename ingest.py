"""
ingest.py — mete un scouting_data.json de CLARA a la memoria de LUCIA.

Uso:
    python ingest.py out/scouting_data.json --roster roster.json \
        --date 2026-06-01 --opponent "Aguilas" --video partido_vs_aguilas.mp4

Correlo una vez por partido. El registro de cada jugadora conocida se apila en
su historia. Re-ingestar el mismo (video, fecha) no duplica (usa --replace para
sobreescribir).
"""
import argparse
from lucia.store import connect, ingest_match


def main():
    p = argparse.ArgumentParser(
        description="Ingesta un scouting_data.json de CLARA a la memoria de LUCIA.")
    p.add_argument("scouting", help="ruta al scouting_data.json (salida de CLARA)")
    p.add_argument("--roster", required=True, help="roster.json (dorsal→jugadora)")
    p.add_argument("--date", required=True, help="fecha del partido (YYYY-MM-DD)")
    p.add_argument("--opponent", default="?", help="rival")
    p.add_argument("--category", default=None,
                   help="categoría/equipo (default: el 'team' del roster)")
    p.add_argument("--video", default=None,
                   help="nombre del video (para el id estable del partido)")
    p.add_argument("--db", default="lucia.db", help="archivo SQLite (default lucia.db)")
    p.add_argument("--replace", action="store_true",
                   help="re-ingesta si el partido ya existe")
    p.add_argument("--rival-side", choices=["A", "B"], default=None,
                   help="si se provee, ingesta también tracks del rival (asume que somos el lado opuesto)")
    a = p.parse_args()

    db = connect(a.db)
    res = ingest_match(db, a.scouting, a.roster, a.date, a.opponent,
                       a.category, a.video, a.replace)
    print(f"[LUCIA] partido {res['match_id']} — {res['status']}")
    print(f"        jugadoras guardadas: {res['players_ingested']} | "
          f"tracks anónimos (rival) descartados: {res['skipped_anonymous']}")

    if a.rival_side:
        from lucia.store import ingest_rival_match
        our_side = "B" if a.rival_side == "A" else "A"
        r_res = ingest_rival_match(db, a.scouting, a.date, a.opponent,
                                   our_side, a.category, a.video, a.replace)
        print(f"        tracks rivales guardados: {r_res['rivals_ingested']}")

if __name__ == "__main__":
    main()
