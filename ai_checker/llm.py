import os
import threading
from pathlib import Path

import httpx

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

_DEFAULT_MODEL_PATH = "C:/models/qwen/Qwen2.5-7B-Instruct.Q4_K.gguf"


def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    if load_dotenv is None:
        return
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _remote_config() -> dict | None:
    _ensure_env_loaded()
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
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
    provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    if provider in {"local", "llama", "llama-cpp"}:
        return False
    if provider in {"remote", "api", "openai", "openrouter", "groq", "mistral"}:
        return True
    return _remote_config() is not None


def _split_prompt(prompt: str) -> tuple[str, str]:
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

    with httpx.Client(timeout=config["timeout"]) as client:
        response = client.post(config["api_url"], headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Remote LLM returned no choices.")
    choice = choices[0]
    if isinstance(choice, dict):
        message = choice.get("message")
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"]).strip()
        if choice.get("text"):
            return str(choice["text"]).strip()
    raise RuntimeError("Remote LLM returned an unexpected response.")


def _resolve_model_path() -> str:
    _ensure_env_loaded()
    env_path = os.getenv("LLM_MODEL_PATH")
    if env_path:
        if Path(env_path).exists():
            return env_path

    default_path = Path(_DEFAULT_MODEL_PATH)
    if default_path.exists():
        return str(default_path)

    alt_default_path = Path("C:/model/qwen/Qwen2.5-7B-Instruct.Q4_K.gguf")
    if alt_default_path.exists():
        return str(alt_default_path)

    root = Path(__file__).resolve().parents[1]
    local_path = root / "models" / "qwen" / "Qwen2.5-7B-Instruct.Q4_K.gguf"
    if local_path.exists():
        return str(local_path)

    alt_local_path = root / "model" / "qwen" / "Qwen2.5-7B-Instruct.Q4_K.gguf"
    if alt_local_path.exists():
        return str(alt_local_path)

    return env_path or ""


def get_model_name() -> str:
    if _use_remote():
        config = _remote_config()
        return config["model"] if config else "remote"
    model_path = _resolve_model_path()
    return Path(model_path).name if model_path else "unknown"


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
                if not model_path or not Path(model_path).exists():
                    raise RuntimeError(
                        "LLM model not found. Set LLM_MODEL_PATH to your .gguf file."
                    )

                n_ctx = int(os.getenv("LLM_CTX", "4096"))
                n_threads = int(
                    os.getenv(
                        "LLM_THREADS",
                        str(max(2, (os.cpu_count() or 8) - 2)),
                    )
                )
                n_batch = int(os.getenv("LLM_BATCH", "512"))
                n_gpu_layers = int(os.getenv("LLM_GPU_LAYERS", "0"))

                _LLM = Llama(
                    model_path=model_path,
                    n_ctx=n_ctx,
                    n_threads=n_threads,
                    n_batch=n_batch,
                    n_gpu_layers=n_gpu_layers,
                    verbose=False,
                )

    return _LLM


def generate_text(
    prompt: str,
    max_tokens: int = 900,
    temperature: float = 0.3,
    top_p: float = 0.9,
) -> str:
    if _use_remote():
        return _generate_remote_text(prompt, max_tokens, temperature, top_p)

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
