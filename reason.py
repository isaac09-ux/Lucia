"""
reason.py — lectura de coach de LUCIA (motor determinista + LLM opcional).

Fase 2: razona sobre la trayectoria de UNA jugadora ya acumulada en la memoria.
Dos piezas con frontera dura (ver lucia/reason.py):
  - motor determinista (compute_facts): aritmética pura, auditable → la verdad.
  - narración (LLM, opcional): vuelve los hechos un párrafo de coach. NO calcula.

Uso:
    python reason.py --player 7                 # solo hechos (motor determinista)
    python reason.py --player 7 --show-prompt   # + lo que recibiría el LLM (sin llamar)
    python reason.py --player 7 --narrate       # + párrafo de coach (LLM)

PRIVACIDAD: por defecto la narración corre LOCAL (Ollama), los hechos no salen
de tu equipo — importante con data de menores. Para apuntar a nube, configura
LUCIA_LLM_BASE_URL / LUCIA_LLM_API_KEY (ver lucia/llm.py).
"""
from lucia.reason import main

if __name__ == "__main__":
    main()
