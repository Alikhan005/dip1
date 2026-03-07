import os
import threading
import logging
from pathlib import Path

import httpx

# Configure module logger.
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None

try:
    from llama_cpp import Llama
except Exception as exc:  # pragma: no cover - import-time error surfaced on use
    Llama = None
    _LLAMA_IMPORT_ERROR = exc
else:
    _LLAMA_IMPORT_ERROR = None

_LLM = None
_INIT_LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()
_ENV_LOADED = False


def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    if load_dotenv is None:
        return
    # Try loading .env from the project root (2 levels above).
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _remote_config() -> dict | None:
    """Load remote LLM settings (OpenAI/Mistral/LocalAI compatible API)."""
    _ensure_env_loaded()
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")

    # If key is missing, remote mode is not configured.
    if not api_key:
        return None

    api_url = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("LLM_REMOTE_MODEL", "").strip() or "gpt-4o-mini"
    timeout = float(os.getenv("LLM_REMOTE_TIMEOUT", "30"))
    org = os.getenv("OPENAI_ORG", "").strip()

    return {
        "api_key": api_key,
        "api_url": api_url,
        "model": model,
        "timeout": timeout,
        "org": org,
    }


def _use_remote() -> bool:
    """Whether remote API should be used instead of local model."""
    provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()

    if provider in {"local", "llama", "llama-cpp"}:
        return False

    if provider in {"remote", "api", "openai", "openrouter", "groq", "mistral"}:
        return True

    # With auto mode try remote only when remote config exists.
    return _remote_config() is not None


def _split_prompt(prompt: str) -> tuple[str, str]:
    """Split prompt to system/user sections for API payload."""
    if "<|im_start|>system" not in prompt:
        return "", prompt
    system = ""
    users = []
    parts = prompt.split("<|im_start|>")
    for part in parts:
        if part.startswith("system\n"):
            system = part[len("system\n") :].split("<|im_end|>", 1)[0].strip()
        elif part.startswith("user\n"):
            user = part[len("user\n") :].split("<|im_end|>", 1)[0].strip()
            if user:
                users.append(user)
    if users:
        return system, "\n\n".join(users)
    return "", prompt


def _generate_remote_text(
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> str:
    config = _remote_config()
    if not config:
        raise RuntimeError("Remote LLM is not configured. Set LLM_API_KEY.")

    system, user = _split_prompt(prompt)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    headers = {"Authorization": f"Bearer {config['api_key']}"}
    if config["org"]:
        headers["OpenAI-Organization"] = config["org"]

    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }

    try:
        with httpx.Client(timeout=config["timeout"]) as client:
            response = client.post(config["api_url"], headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.error(f"Error calling remote LLM: {e}")
        raise RuntimeError(f"Remote LLM connection failed: {e}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Remote LLM returned no choices.")

    choice = choices[0]
    # Support both chat and completion-style response formats.
    if isinstance(choice, dict):
        message = choice.get("message")
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"]).strip()
        if choice.get("text"):
            return str(choice["text"]).strip()

    raise RuntimeError("Remote LLM returned an unexpected response.")


def _resolve_model_path() -> str:
    """
    Resolve local model path (used only for explicit local provider runs).
    Supported source:
    1. LLM_MODEL_PATH env variable.
    """
    _ensure_env_loaded()
    env_path = os.getenv("LLM_MODEL_PATH")
    if env_path and Path(env_path).exists():
        logger.info(f"Using model from env: {env_path}")
        return env_path
    if env_path:
        logger.warning(f"LLM_MODEL_PATH is set but file does not exist: {env_path}")

    logger.warning(
        "No local model path found. Set LLM_MODEL_PATH for local mode "
        "or configure remote API (LLM_PROVIDER=remote / LLM_API_KEY)."
    )
    return ""


def get_model_name() -> str:
    if _use_remote():
        config = _remote_config()
        return config["model"] if config else "remote"
    model_path = _resolve_model_path()
    return Path(model_path).name if model_path else "unknown"


def warmup_llm() -> str:
    """
    Best-effort warmup to reduce first-request latency.
    Returns selected model/provider name.
    """
    if _use_remote():
        return get_model_name()
    get_llm()
    return get_model_name()


def get_llm() -> "Llama":
    if Llama is None:
        raise RuntimeError(
            "llama-cpp-python is not installed or failed to import: "
            f"{_LLAMA_IMPORT_ERROR}. Install with: pip install llama-cpp-python"
        )

    global _LLM
    if _LLM is None:
        with _INIT_LOCK:
            if _LLM is None:
                model_path = _resolve_model_path()

                # If model path is invalid, fail with a clear error.
                if not model_path or not Path(model_path).exists():
                    raise RuntimeError(
                        f"LLM model not found at '{model_path}'. "
                        "Please set LLM_MODEL_PATH in .env to your .gguf file location."
                    )

                # Load runtime parameters from .env or defaults.
                n_ctx = int(os.getenv("LLM_CTX", "4096"))

                # Auto-thread heuristic keeps 2 cores for the system.
                default_threads = max(1, (os.cpu_count() or 4) - 2)
                n_threads = int(os.getenv("LLM_THREADS", str(default_threads)))

                n_batch = int(os.getenv("LLM_BATCH", "512"))
                n_gpu_layers = int(os.getenv("LLM_GPU_LAYERS", "0"))

                logger.info(f"Loading Llama model from {model_path} (ctx={n_ctx}, threads={n_threads})...")

                try:
                    _LLM = Llama(
                        model_path=model_path,
                        n_ctx=n_ctx,
                        n_threads=n_threads,
                        n_batch=n_batch,
                        n_gpu_layers=n_gpu_layers,
                        verbose=False,
                    )
                    logger.info("Model loaded successfully.")
                except Exception as e:
                    logger.error(f"Failed to load Llama model: {e}")
                    raise RuntimeError(f"Failed to initialize Llama model: {e}")

    return _LLM


def generate_text(
    prompt: str,
    max_tokens: int = 900,
    temperature: float = 0.3,
    top_p: float = 0.9,
) -> str:
    """
    High-level text generation entry point.
    Chooses remote API first, then local model.
    """
    # 1. Try remote API first when enabled.
    if _use_remote():
        try:
            return _generate_remote_text(prompt, max_tokens, temperature, top_p)
        except Exception as e:
            # If remote fails, rethrow. No local fallback is executed unless
            # provider is configured to allow it.
            logger.error(f"Remote generation failed: {e}")
            raise e

    # 2. Fallback to local model when remote is disabled.
    llm = get_llm()
    with _RUN_LOCK:
        output = llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=["<|im_end|>"],
        )
    return output["choices"][0]["text"].strip()
