"""
query.py — lee trayectorias de la memoria de LUCIA (v0, sin LLM).

Uso:
    python query.py player 7            # historia de la #7 partido por partido
    python query.py trend distance_m    # tendencia de equipo en una métrica

Esto es la fase 1: data cruda consultable. La lectura de coach (Claude sobre
la historia + tu metodología FIVB) se monta encima cuando haya partidos cargados.
"""
import argparse
from lucia.store import connect, player_history, team_metric, SCALAR_METRICS


def main():
    p = argparse.ArgumentParser(
        description="Lee la trayectoria de una jugadora o una tendencia de equipo.")
    p.add_argument("--db", default="lucia.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("player", help="historia de una jugadora")
    pp.add_argument("jersey", type=int)

    pt = sub.add_parser("trend", help="tendencia de equipo en una métrica escalar")
    pt.add_argument("metric", choices=list(SCALAR_METRICS))

    a = p.parse_args()
    db = connect(a.db)

    if a.cmd == "player":
        rows = player_history(db, a.jersey)
        if not rows:
            print(f"sin registros para la #{a.jersey}")
            return
        name = rows[0]["player_name"]
        print(f"#{a.jersey} {name} — {len(rows)} partido(s)")
        for r in rows:
            print(f"  {r['date']} vs {str(r['opponent']):<12} | "
                  f"zona dom {str(r['dominant_zone']):<3} | "
                  f"{r['distance_m']} m | {r['avg_speed_m_per_s']} m/s | "
                  f"fiab {r['reliability']}")

    elif a.cmd == "trend":
        data = team_metric(db, a.metric)
        if not data:
            print("memoria vacía — ingesta algún partido primero")
            return
        for (jersey, name), series in sorted(data.items()):
            pts = "  ".join(f"{d}:{v}" for d, v in series)
            print(f"#{jersey} {str(name):<12} {a.metric}: {pts}")


if __name__ == "__main__":
    main()
