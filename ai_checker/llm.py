import os
import threading
from pathlib import Path

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


def _resolve_model_path() -> str:
    _ensure_env_loaded()
    env_path = os.getenv("LLM_MODEL_PATH")
    if env_path:
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
