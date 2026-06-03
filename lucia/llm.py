"""
lucia.llm — cliente del LLM para la capa de lenguaje (narrate).

Habla con cualquier endpoint OpenAI-compatible vía POST /chat/completions, sin
dependencias (urllib de la stdlib). Por defecto apunta a Ollama LOCAL, donde la
narración corre en TU máquina.

PRIVACIDAD (importante para data de menores):
- Ollama LOCAL (default): los hechos NUNCA salen de tu equipo. No necesitas key
  real — el placeholder "ollama" basta.
- NUBE (Ollama Cloud, OpenRouter, DeepInfra, etc.): pon LUCIA_LLM_BASE_URL y
  LUCIA_LLM_API_KEY. Ojo: los hechos viajan a ese servidor.

Config por variables de entorno (o argumentos a chat()):
    LUCIA_LLM_BASE_URL   default http://localhost:11434/v1   (Ollama local)
    LUCIA_LLM_API_KEY    default "ollama"                     (placeholder local)
    LUCIA_LLM_MODEL      default "gemma4"
"""
import json
import os
import urllib.request

DEFAULT_BASE_URL = os.environ.get("LUCIA_LLM_BASE_URL", "http://localhost:11434/v1")
DEFAULT_API_KEY = os.environ.get("LUCIA_LLM_API_KEY", "ollama")
DEFAULT_MODEL = os.environ.get("LUCIA_LLM_MODEL", "gemma4")


class LLMError(RuntimeError):
    pass


def chat(messages, model=None, base_url=None, api_key=None,
         temperature=0.3, timeout=120):
    """
    POST a /chat/completions (OpenAI-compatible). Devuelve el texto del modelo.
    `messages` = lista de {role, content} (lo que arma reason.build_messages).
    """
    model = model or DEFAULT_MODEL
    base_url = base_url or DEFAULT_BASE_URL
    api_key = api_key or DEFAULT_API_KEY

    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except Exception as e:
        raise LLMError(
            f"No pude hablar con el LLM en {url} (modelo '{model}'). "
            f"Si es local: ¿corriste `ollama serve` y `ollama pull {model}`? "
            f"Si es nube: revisa LUCIA_LLM_BASE_URL y LUCIA_LLM_API_KEY. "
            f"Detalle: {e}") from e

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Respuesta inesperada del LLM: {data}") from e
