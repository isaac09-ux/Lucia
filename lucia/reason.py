"""
lucia.reason — motor de razonamiento HÍBRIDO de LUCIA.

Dos piezas, con una FRONTERA DURA entre ellas:

  1) compute_facts()  — MOTOR DETERMINISTA. Toma la historia de una jugadora
     (del store) y calcula hechos: últimos valores, deltas, tendencia
     (sube/baja/plano), media móvil, banderas por regla. Aritmética pura,
     auditable, testeable. Es la FUENTE DE VERDAD.

  2) narrate()        — CAPA DE LENGUAJE (LLM, opcional, "por comodidad").
     Toma SOLO los hechos del motor y los vuelve un párrafo de coach. NUNCA
     calcula ni inventa una cifra: si un número aparece en su texto, salió tal
     cual de compute_facts(). El LLM narra; el motor calcula.

Por qué la frontera: los LLM alucinan estadística. Si el LLM toca los números,
pierdes lo único que hace confiable a LUCIA. El motor es TU IP; el LLM es
commodity intercambiable (Kimi / Claude / local vía Ollama).
"""
import argparse
import json
from pathlib import Path

# Métricas escalares con tendencia (las que hoy emite el store; el jump_index
# entra aquí en cuanto lo ingestes como una métrica más por partido).
SCALAR_METRICS = ("distance_m", "avg_speed_m_per_s", "seconds_tracked", "samples")
FLAT_EPS_FRAC = 0.05   # cambio < 5% del valor previo = "plano"


# ─────────────────────────── MOTOR DETERMINISTA ───────────────────────────

def _direction(prev, latest):
    if prev in (None, 0):
        return "n/a"
    change = (latest - prev) / abs(prev)
    if abs(change) < FLAT_EPS_FRAC:
        return "plano"
    return "sube" if change > 0 else "baja"


def _trend(values):
    """values: lista cronológica de floats (None se omite)."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    latest = float(vals[-1])
    prev = float(vals[-2]) if len(vals) >= 2 else None
    tail = vals[-3:]
    out = {
        "latest": round(latest, 2),
        "prev": round(prev, 2) if prev is not None else None,
        "n": len(vals),
        "ma3": round(sum(tail) / len(tail), 2),
        "direction": _direction(prev, latest),
    }
    if prev is not None:
        out["delta"] = round(latest - prev, 2)
    return out


def _monotonic(values, k=3, rising=True):
    vals = [v for v in values if v is not None]
    if len(vals) < k:
        return False
    last = vals[-k:]
    if rising:
        return all(last[i] < last[i + 1] for i in range(len(last) - 1))
    return all(last[i] > last[i + 1] for i in range(len(last) - 1))


def compute_facts(history):
    """
    history: lista de registros por partido de UNA jugadora (de
    store.player_history), en orden cronológico. Devuelve hechos estructurados.
    Cero LLM — esto es la fuente de verdad.
    """
    if not history:
        return None
    metrics = {}
    for m in SCALAR_METRICS:
        t = _trend([r.get(m) for r in history])
        if t:
            metrics[m] = t

    # ── Banderas (reglas). Hoy solo OBJETIVAS — no requieren tu criterio. ──
    # Aquí es donde, con el tiempo, codificas TU metodología FIVB como reglas.
    flags = []
    if _monotonic([r.get("distance_m") for r in history], rising=False):
        flags.append("distancia recorrida baja 3+ partidos seguidos "
                     "(posible fatiga o menos minutos en cancha)")
    if _monotonic([r.get("avg_speed_m_per_s") for r in history], rising=True):
        flags.append("velocidad media sube 3+ partidos (mejora física)")

    return {
        "jersey": history[0].get("jersey"),
        "player_name": history[0].get("player_name"),
        "n_matches": len(history),
        "metrics": metrics,
        "flags": flags,
    }


# ─────────────────────────── CAPA DE LENGUAJE (LLM) ───────────────────────────

SYSTEM_PROMPT = (
    "Eres el asistente analítico de un entrenador de voleibol FIVB. Te paso "
    "HECHOS ya calculados sobre una jugadora; tu trabajo es explicárselos al "
    "coach en español claro y proponer 2-3 cosas concretas a trabajar.\n"
    "REGLA ABSOLUTA: usa SOLO los números que están en los hechos. NO inventes, "
    "estimes ni calcules ninguna cifra nueva. Si un dato no aparece, no lo "
    "menciones. Tú narras; los números ya vienen calculados por el motor."
)


def build_messages(facts):
    """Mensajes que se ENVIARÍAN al LLM. Inspeccionable sin llamar a nada."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content":
            "HECHOS (no agregues números fuera de aquí):\n"
            + json.dumps(facts, ensure_ascii=False, indent=2)
            + "\n\nDame un resumen de 2-3 líneas y luego 2-3 cosas a trabajar, "
              "en viñetas."},
    ]


def narrate(facts, call=None, **llm_kwargs):
    """
    CAPA DE LENGUAJE (opcional, "por comodidad"). Convierte los hechos en prosa.
    - Sin `call`: devuelve los mensajes que se enviarían (para verlos). NO llama.
    - Con `call` (p.ej. `lucia.llm.chat`): hace la llamada. `call(messages,
      **llm_kwargs)` debe devolver el texto del modelo. El modelo es
      intercambiable (Gemma local / Kimi nube / Claude) sin tocar el motor.
    NUNCA calcula: solo narra los `facts` del motor determinista.
    """
    messages = build_messages(facts)
    if call is None:
        return {"_sin_llm": True, "messages": messages}
    return call(messages, **llm_kwargs)


# ─────────────────────────── CLI ───────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Razonamiento híbrido de LUCIA: motor determinista (+ LLM opcional).")
    ap.add_argument("--db", default="lucia.db")
    ap.add_argument("--player", type=int, required=True, help="dorsal")
    ap.add_argument("--narrate", action="store_true",
                    help="genera el párrafo de coach con el LLM (Ollama por defecto)")
    ap.add_argument("--model", default=None, help="modelo LLM (default: env o gemma4)")
    ap.add_argument("--base-url", default=None,
                    help="endpoint OpenAI-compatible (default: Ollama local)")
    ap.add_argument("--show-prompt", action="store_true",
                    help="muestra los mensajes que se mandarían al LLM (sin llamar)")
    a = ap.parse_args()

    from lucia.store import connect, player_history
    db = connect(a.db)
    facts = compute_facts(player_history(db, a.player))
    if facts is None:
        print(f"sin historia para la #{a.player}")
        return

    print("── HECHOS (motor determinista, fuente de verdad) ──")
    print(json.dumps(facts, ensure_ascii=False, indent=2))

    if a.narrate:
        from lucia.llm import chat, LLMError
        kwargs = {}
        if a.model:
            kwargs["model"] = a.model
        if a.base_url:
            kwargs["base_url"] = a.base_url
        print("\n── PÁRRAFO DE COACH (el LLM narra los hechos) ──")
        try:
            print(narrate(facts, call=chat, **kwargs))
        except LLMError as e:
            print(f"[LLM no disponible] {e}")
    elif a.show_prompt:
        print("\n── lo que recibiría el LLM (solo narra esto) ──")
        print(json.dumps(narrate(facts), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
