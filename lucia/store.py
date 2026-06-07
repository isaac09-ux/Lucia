"""
lucia.store — capa de memoria longitudinal de LUCIA.

CLARA son los ojos: procesa UN partido y escribe scouting_data.json. Esto es el
sustrato de memoria que convierte esos snapshots sueltos en TRAYECTORIAS por
jugadora a lo largo de todos los partidos.

CONEXIÓN CON CLARA — solo por el contrato de archivo:
    Este módulo LEE el scouting_data.json que CLARA escribe. No importa nada de
    CLARA, ni CLARA importa nada de aquí. El único punto del código donde se
    interpreta el formato de CLARA es `ingest_match`. Si CLARA cambia su salida,
    se ajusta aquí y en ningún otro lado.

ALMACENAMIENTO:
    SQLite — un archivo, cero dependencias (sqlite3 es stdlib), consultable.
    Se guardan columnas escalares para consultar tendencias rápido + la ficha
    CRUDA completa del track en una columna JSON, para no perder nunca nada de
    lo que CLARA saca (aunque hoy no lo usemos).

DISEÑO v0 (sin LLM): solo acumula y deja consultar. El razonamiento (Claude como
segundo coach) se monta encima cuando ya haya 3-4 partidos cargados.
"""
import json
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id     TEXT PRIMARY KEY,
    date         TEXT,
    opponent     TEXT,
    category     TEXT,
    video        TEXT,
    ingested_at  TEXT,
    n_rallies    INTEGER,
    total_play_s REAL,
    raw          TEXT          -- stats de rally crudas (JSON)
);
CREATE TABLE IF NOT EXISTS player_match (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id           TEXT NOT NULL REFERENCES matches(match_id),
    jersey             INTEGER NOT NULL,
    player_name        TEXT,
    reliability        TEXT,
    samples            INTEGER,
    seconds_tracked    REAL,
    distance_m         REAL,
    avg_speed_m_per_s  REAL,
    jump_index         REAL,
    touch_rallies      REAL,
    side               TEXT,
    dominant_zone      TEXT,
    zone_profile_pct   TEXT,   -- JSON {zona: pct}
    avg_court_pos_m    TEXT,   -- JSON [x, y]
    pose_stats         TEXT,   -- JSON (None sin --pose)
    clara_reason_notes TEXT,   -- JSON array of semantic flags from clara_reason
    raw                TEXT,   -- ficha COMPLETA del track (JSON) — lossless
    UNIQUE(match_id, jersey)
);
CREATE TABLE IF NOT EXISTS rival_match (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id         TEXT NOT NULL REFERENCES matches(match_id),
    jersey           INTEGER,          -- may be None if unrecognized
    track_idx        INTEGER,          -- sequential index within the match
    samples          INTEGER,
    seconds_tracked  REAL,
    distance_m       REAL,
    avg_speed_m_per_s REAL,
    side             TEXT,
    dominant_zone    TEXT,
    zone_profile_pct TEXT,             -- JSON
    avg_court_pos_m  TEXT,             -- JSON
    raw              TEXT              -- full track JSON, lossless
);
"""

# Llaves de resumen de rally que emite clara.py
_RALLY_KEYS = ("n_rallies", "n_serves", "avg_rally_s", "longest_rally_s",
               "total_play_s", "serves_by_side")
# Métricas escalares consultables en tendencias de equipo
SCALAR_METRICS = ("distance_m", "avg_speed_m_per_s", "seconds_tracked", "samples")


def migrate_v1(db):
    """Add jump_index and touch_rallies columns if they don't exist yet
    (for databases created before v1)."""
    try:
        db.execute("ALTER TABLE player_match ADD COLUMN jump_index REAL")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE player_match ADD COLUMN touch_rallies REAL")
    except sqlite3.OperationalError:
        pass

def connect(db_path):
    """Abre (o crea) la base y garantiza el esquema."""
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    migrate_v1(db)
    return db


def _match_id(video, date):
    """ID estable: mismo (video, fecha) => mismo id. Re-ingestar no duplica."""
    return hashlib.sha1(f"{video}|{date}".encode()).hexdigest()[:12]


def ingest_match(db, scouting_path, roster_path, date, opponent,
                 category=None, video=None, replace=False, clara_reason_path=None):
    """
    Dobla un scouting_data.json (un partido) en la historia por jugadora.

    Solo se guardan jugadoras presentes en el roster (dorsal reconocido). Los
    tracks anónimos (rivales) se descartan — igual que el diseño de CLARA.
    """
    scouting = json.loads(Path(scouting_path).read_text())
    roster = json.loads(Path(roster_path).read_text())
    players = {str(k): v for k, v in roster.get("players", {}).items()}
    category = category or roster.get("team")
    video = video or Path(scouting_path).stem
    mid = _match_id(video, date)
    
    clara_reason = []
    if clara_reason_path:
        cr_path = Path(clara_reason_path)
        if cr_path.exists():
            clara_reason = json.loads(cr_path.read_text())

    exists = db.execute("SELECT 1 FROM matches WHERE match_id=?", (mid,)).fetchone()
    if exists:
        if not replace:
            return {"match_id": mid, "status": "ya existe (usa --replace)",
                    "players_ingested": 0, "skipped_anonymous": 0}
        db.execute("DELETE FROM player_match WHERE match_id=?", (mid,))
        db.execute("DELETE FROM matches WHERE match_id=?", (mid,))

    rally = {k: scouting.get(k) for k in _RALLY_KEYS}
    db.execute(
        "INSERT INTO matches(match_id,date,opponent,category,video,ingested_at,"
        "n_rallies,total_play_s,raw) VALUES(?,?,?,?,?,?,?,?,?)",
        (mid, date, opponent, category, video,
         datetime.now(timezone.utc).isoformat(timespec="seconds"),
         scouting.get("n_rallies"), scouting.get("total_play_s"),
         json.dumps(rally, ensure_ascii=False)))

    ingested = skipped = 0
    for t in scouting.get("tracks", []):
        jersey = t.get("id")
        name = players.get(str(jersey))
        if name is None:
            skipped += 1          # track anónimo (rival) — por diseño no se guarda
            continue
            
        track_flags = []
        for cr in clara_reason:
            if cr.get("jersey") == jersey or cr.get("clip_id") == t.get("clip_id"):
                track_flags.extend(cr.get("flags", []))
                
        db.execute(
            "INSERT INTO player_match(match_id,jersey,player_name,reliability,"
            "samples,seconds_tracked,distance_m,avg_speed_m_per_s,jump_index,"
            "touch_rallies,side,dominant_zone,zone_profile_pct,avg_court_pos_m,"
            "pose_stats,clara_reason_notes,raw)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid, jersey, name, t.get("reliability"), t.get("samples"),
             t.get("seconds_tracked"), t.get("distance_m"),
             t.get("avg_speed_m_per_s"), t.get("jump_index"),
             t.get("touch_rallies"), t.get("side"), t.get("dominant_zone"),
             json.dumps(t.get("zone_profile_pct"), ensure_ascii=False),
             json.dumps(t.get("avg_court_pos_m")),
             json.dumps(t.get("pose_stats"), ensure_ascii=False),
             json.dumps(track_flags, ensure_ascii=False) if track_flags else None,
             json.dumps(t, ensure_ascii=False)))
        ingested += 1

    db.commit()
    return {"match_id": mid, "status": "ok",
            "players_ingested": ingested, "skipped_anonymous": skipped}


def ingest_rival_match(db, scouting_path, date, opponent,
                       our_side, category=None, video=None, replace=False):
    """
    Ingests the OPPONENT tracks from a scouting_data.json.
    our_side: "A" or "B" — which side is Las Chispas.
    Stores all tracks where side != our_side (or side is None).
    Returns: {"match_id": ..., "status": ..., "rivals_ingested": N}
    """
    scouting = json.loads(Path(scouting_path).read_text())
    category = category
    video = video or Path(scouting_path).stem
    mid = _match_id(video, date)

    if replace:
        db.execute("DELETE FROM rival_match WHERE match_id=?", (mid,))

    ingested = 0
    for idx, t in enumerate(scouting.get("tracks", [])):
        side = t.get("side")
        if side != our_side:
            db.execute(
                "INSERT INTO rival_match(match_id,jersey,track_idx,samples,"
                "seconds_tracked,distance_m,avg_speed_m_per_s,side,dominant_zone,"
                "zone_profile_pct,avg_court_pos_m,raw) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, t.get("id"), idx, t.get("samples"), t.get("seconds_tracked"),
                 t.get("distance_m"), t.get("avg_speed_m_per_s"), side,
                 t.get("dominant_zone"), json.dumps(t.get("zone_profile_pct"), ensure_ascii=False),
                 json.dumps(t.get("avg_court_pos_m")), json.dumps(t, ensure_ascii=False))
            )
            ingested += 1
    db.commit()
    return {"match_id": mid, "status": "ok", "rivals_ingested": ingested}


def rival_history(db, opponent_name):
    """All rival tracks for a given opponent name, ordered by date."""
    rows = db.execute(
        "SELECT m.date, m.opponent, r.* FROM rival_match r "
        "JOIN matches m ON m.match_id=r.match_id "
        "WHERE m.opponent=? ORDER BY m.date", (opponent_name,)).fetchall()
    return [dict(r) for r in rows]

def player_history(db, jersey):
    """Todos los registros de una jugadora, ordenados por fecha de partido."""
    rows = db.execute(
        "SELECT m.date, m.opponent, pm.* FROM player_match pm "
        "JOIN matches m ON m.match_id=pm.match_id "
        "WHERE pm.jersey=? ORDER BY m.date", (jersey,)).fetchall()
    return [dict(r) for r in rows]


def team_metric(db, metric):
    """Serie por jugadora de una métrica escalar a lo largo de los partidos."""
    if metric not in SCALAR_METRICS:
        raise ValueError(f"métrica debe ser una de {SCALAR_METRICS}")
    rows = db.execute(
        f"SELECT pm.jersey, pm.player_name, m.date, pm.{metric} AS val "
        "FROM player_match pm JOIN matches m ON m.match_id=pm.match_id "
        "ORDER BY pm.jersey, m.date").fetchall()
    out = {}
    for r in rows:
        out.setdefault((r["jersey"], r["player_name"]), []).append((r["date"], r["val"]))
    return out
