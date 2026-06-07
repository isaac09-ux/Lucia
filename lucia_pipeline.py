"""
lucia_pipeline.py — orquestador CLARA → LUCIA.

Uso rápido:
  python lucia_pipeline.py partido.mp4 \
      --roster roster.json --date 2026-06-07 --opponent "Tigres" \
      --calibration cal.json --reason --narrate

Corre CLARA, ingesta en lucia.db, imprime hechos y (opcional) narración de coach.
"""

import sys
import argparse
import subprocess
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Orquestador CLARA -> LUCIA")
    parser.add_argument("video", help="Video a procesar")
    parser.add_argument("--roster", required=True, help="roster.json")
    parser.add_argument("--date", required=True, help="Fecha del partido (YYYY-MM-DD)")
    parser.add_argument("--opponent", required=True, help="Rival")
    parser.add_argument("--db", default="lucia.db", help="Archivo SQLite")
    parser.add_argument("--clara", default="../CLARA/src/clara.py", help="Ruta a clara.py")
    parser.add_argument("--calibration", help="Archivo de calibración")
    parser.add_argument("--clara-reason", help="Ruta a clara_reason.py")
    parser.add_argument("--play-gate", action="store_true", help="Pasar --play-gate a clara.py")
    parser.add_argument("--event-labels", action="store_true", help="Pasar --event-labels a clara.py")
    parser.add_argument("--rival-side", choices=["A", "B"], help="Si se provee, ingesta tracks rivales")
    parser.add_argument("--reason", action="store_true", help="Imprimir hechos para jugadores")
    parser.add_argument("--narrate", action="store_true", help="Llamar narración LLM (requiere --reason)")
    parser.add_argument("--player", type=int, help="Solo jugador #N para --reason")
    parser.add_argument("--out-dir", default="out/", help="Directorio de salida de CLARA")
    
    args = parser.parse_args()
    
    video_path = Path(args.video)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    scouting_json = out_dir / "scouting_data.json"
    reason_json = out_dir / "scouting_data_reason.json"
    
    # STEP 1 — Run CLARA
    clara_path = Path(args.clara)
    if not clara_path.exists():
        print(f"Error: No se encontró clara.py en {clara_path}")
        sys.exit(1)
        
    print(f"[*] Corriendo CLARA sobre {args.video}...")
    clara_cmd = [sys.executable, str(clara_path), str(video_path), "--out-dir", str(out_dir)]
    if args.calibration:
        clara_cmd.extend(["--calibration", args.calibration])
    if args.play_gate:
        clara_cmd.append("--play-gate")
    if args.event_labels:
        clara_cmd.append("--event-labels")
        
    try:
        subprocess.run(clara_cmd, check=True)
    except subprocess.CalledProcessError:
        print("Error: Falló el paso de CLARA")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: No se pudo ejecutar {sys.executable}. Verifique su entorno.")
        sys.exit(1)
        
    if not scouting_json.exists():
        print(f"Error: CLARA terminó pero no se encontró el archivo esperado: {scouting_json}")
        sys.exit(1)
        
    # STEP 2 — Run clara_reason (optional)
    if args.clara_reason:
        print("[*] Corriendo clara_reason...")
        cr_path = Path(args.clara_reason)
        if not cr_path.exists():
            print(f"Error: No se encontró clara_reason.py en {cr_path}")
            sys.exit(1)
            
        cr_cmd = [sys.executable, str(cr_path), str(scouting_json), "--out", str(reason_json)]
        try:
            subprocess.run(cr_cmd, check=True)
        except subprocess.CalledProcessError:
            print("Error: Falló el paso de clara_reason")
            sys.exit(1)
            
    # STEP 3 — Ingest into LUCIA
    print("[*] Ingestando datos en LUCIA...")
    try:
        from lucia.store import connect, ingest_match, ingest_rival_match
    except ImportError:
        print("Error: No se pudieron importar los módulos de lucia. Asegúrese de estar en el directorio raíz del repo.")
        sys.exit(1)
        
    db = connect(args.db)
    res = ingest_match(
        db, str(scouting_json), args.roster, args.date, args.opponent,
        video=str(video_path),
        clara_reason_path=str(reason_json) if reason_json.exists() else None
    )
    
    print(f"[LUCIA] partido {res['match_id']} — {res['status']}")
    print(f"        jugadoras guardadas: {res['players_ingested']} | tracks anónimos descartados: {res['skipped_anonymous']}")
    
    if args.rival_side:
        # Opposite side for rivals as per task description
        our_side = "B" if args.rival_side == "A" else "A"
        r_res = ingest_rival_match(db, str(scouting_json), args.date, args.opponent,
                                   our_side=our_side, video=str(video_path))
        print(f"        tracks rivales guardados: {r_res['rivals_ingested']}")
        
    # STEP 4 — Reason (optional)
    if args.reason:
        print("\n── RAZONAMIENTO ──")
        try:
            from lucia.reason import compute_facts, narrate
            from lucia.store import player_history
        except ImportError:
            print("Error: No se pudieron importar los módulos de lucia.reason.")
            sys.exit(1)
            
        mid = res["match_id"]
        if args.player:
            jerseys = [args.player]
        else:
            rows = db.execute("SELECT jersey FROM player_match WHERE match_id=?", (mid,)).fetchall()
            jerseys = [r["jersey"] for r in rows]
            
        for jersey in jerseys:
            history = player_history(db, jersey)
            facts = compute_facts(history)
            if not facts:
                print(f"No hay historia para #{jersey}")
                continue
                
            print(f"\n[Jugadora #{jersey} - {facts.get('player_name', '?')}]")
            print(json.dumps(facts, ensure_ascii=False, indent=2))
            
            if args.narrate:
                try:
                    from lucia.llm import chat
                    print("\n[Narración de Coach]")
                    print(narrate(facts, call=chat))
                except Exception as e:
                    print(f"[LLM Error] {e}")

if __name__ == "__main__":
    main()
