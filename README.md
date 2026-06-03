# LUCIA

El cerebro. CLARA son los ojos (un partido → `scouting_data.json`); LUCIA acumula
esos partidos en **trayectorias por jugadora** y, encima, razona sobre ellas para
decidir qué desarrollar en cada niña a lo largo del tiempo.

> Filosofía: "excelentes ante los demás" no se mide contra USA — se mide contra
> el yo de cada jugadora de hace tres meses. LUCIA es el instrumento que vuelve
> ese trayecto medible.

## Relación con CLARA

CLARA es un **componente** de LUCIA (su tentáculo de visión), y vive en su propia
repo. LUCIA y CLARA se conectan **solo por el contrato de archivo**:

```
footage → CLARA → scouting_data.json ─┐
                                       ├─► LUCIA ingest → memoria por jugadora → trayectorias → coach
                          roster.json ─┘
```

LUCIA **no importa** nada de CLARA ni viceversa. El único punto del código que
interpreta la salida de CLARA es `lucia/store.py::ingest_match`. Si CLARA cambia
su `scouting_data.json`, se ajusta ahí y en ningún otro lado. CLARA no se toca.

## Qué hay hoy (v0 — sin LLM)

El sustrato: acumular y consultar. Cero decisiones que bloqueen — solo guarda
**todo** lo que CLARA ya saca por jugadora (zona dominante, perfil de zonas,
distancia, velocidad, fiabilidad, posición media, pose), por partido.

- `lucia/store.py` — esquema SQLite + ingesta + consultas.
- `ingest.py` — mete un `scouting_data.json` a la memoria.
- `query.py` — lee la trayectoria de una jugadora o una tendencia de equipo.

Almacenamiento: SQLite (un archivo, stdlib, consultable). Las jugadoras rival
quedan fuera a propósito (solo se guardan dorsales del roster), igual que CLARA.

## Uso

```bash
# Una vez por partido
python ingest.py out/scouting_data.json --roster roster.json \
    --date 2026-06-01 --opponent "Tigres" --video p2.mp4

# Leer trayectorias
python query.py player 7          # historia de la #7, partido por partido
python query.py trend distance_m  # tendencia de equipo en una métrica
```

Prueba con la data de ejemplo en `examples/` (dos partidos, la #7 en ambos).

## Roadmap

- **Fase 0 (hecho):** sustrato — acumular `scouting_data.json` en historia por jugadora.
- **Fase 1 (hecho, parcial):** consultas crudas — trayectoria por jugadora, tendencias de equipo.
- **Fase 2:** primera lectura de coach — Claude (API) sobre la historia de UNA jugadora
  + metodología FIVB → "qué drillear". Aquí nace la segunda cabeza.
- **Fase 3:** cuando los prompts se pongan difíciles de mantener y haya ejemplos
  para optimizar → `context-engineering-dspy` para orquestar las cabezas
  (técnica/táctica/psicológica) + patrón `mem0`/Qdrant para memoria escalable
  por jugadora y por rival.
