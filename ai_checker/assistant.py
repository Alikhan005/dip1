import os
import re
import threading
from pathlib import Path

from .llm import generate_text, get_model_name
from .services import build_syllabus_text

_GUIDELINES = None
_GUIDELINES_LOCK = threading.Lock()
_ENV_LOADED = False

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None


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

def _env_int(name: str, default: int) -> int:
    _ensure_env_loaded()
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_str(name: str, default: str) -> str:
    _ensure_env_loaded()
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _assistant_mode() -> str:
    return _env_str("LLM_ASSISTANT_MODE", "auto").lower()


def _is_fast_mode(mode: str | None = None) -> bool:
    if mode is None:
        mode = _assistant_mode()
    return mode in {"fast", "rules", "off", "0"}


def _should_fallback(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "llama-cpp-python" in message
        or "llama_cpp" in message
        or "llm model not found" in message
    )

_GUIDELINES_LIMIT = _env_int("LLM_GUIDELINES_LIMIT", 2000)
_PDF_GUIDELINES_LIMIT = _env_int("LLM_GUIDELINES_PDF_LIMIT", 1600)
_PDF_GUIDELINES_PAGES = _env_int("LLM_GUIDELINES_PDF_PAGES", 2)
_ASSISTANT_SYLLABUS_LIMIT = _env_int("LLM_ASSISTANT_SYLLABUS_LIMIT", 2500)
_ASSISTANT_MAX_TOKENS = _env_int("LLM_ASSISTANT_MAX_TOKENS", 220)

_GREETING_CLEAN_RE = re.compile(r"[^\\w\\s\\-]+", re.UNICODE)
_FAST_GREETINGS = {
    "привет",
    "здравствуйте",
    "добрый день",
    "добрый вечер",
    "доброе утро",
    "hi",
    "hello",
}

def _fast_reply(message: str) -> str | None:
    cleaned = _GREETING_CLEAN_RE.sub("", message).strip().lower()
    if cleaned in _FAST_GREETINGS:
        return (
            "Здравствуйте! Напишите, что нужно сделать с силлабусом: "
            "темы, недели, часы, литература или вопросы."
        )
    return None


def _rules_only_answer(message: str) -> str:
    text = message.strip().lower()
    if not text:
        return (
            "Напишите, что нужно проверить: "
            "темы, недели, часы, литературу или вопросы."
        )

    if "силлабус" in text and any(
        word in text for word in ("созд", "сдел", "собер", "сформир", "оформ")
    ):
        return (
            "Чтобы создать силлабус:\n"
            "1) Перейдите в раздел \"Силлабусы\" и нажмите \"Создать\".\n"
            "2) Выберите курс, язык, семестр и количество недель.\n"
            "3) Добавьте темы из банка тем (или сначала создайте тему в разделе \"Курсы\").\n"
            "4) Проверьте часы, литературу и контрольные вопросы по темам.\n"
            "5) Сохраните черновик и отправьте на согласование декану."
        )

    if "недел" in text or "week" in text:
        return (
            "Проверьте покрытие недель: "
            "нет ли пропусков и дублей, "
            "количество недель должно совпадать с планом."
        )

    if "час" in text or "hour" in text:
        return (
            "Часы должны сходиться с общей нормой "
            "и быть распределены по неделям. "
            "Укажите аудиторные часы и СРС/СРО."
        )

    if "литератур" in text or "literatur" in text:
        return (
            "Добавьте минимум 2-3 источника "
            "на каждую крупную тему, "
            "укажите автора, год и название."
        )

    if "вопрос" in text or "question" in text:
        return (
            "Добавьте 2-4 контрольных вопроса "
            "по каждой теме, чтобы они проверяли "
            "ключевые понятия."
        )

    if "тем" in text or "topic" in text:
        return (
            "Укажите четкое название темы, "
            "краткое описание и ожидаемые результаты."
        )

    return (
        "Могу помочь по силлабусу: создать, заполнить темы, недели, часы, литературу "
        "и вопросы, проверить ошибки. "
        "Опишите задачу одной фразой, например: \"создать силлабус\", "
        "\"проверить недели\", \"добавить литературу\"."
    )


_SYLLABUS_HINTS = (
    "силлабус",
    "syllabus",
    "курс",
    "course",
    "тема",
    "темы",
    "topic",
    "недел",
    "week",
    "час",
    "hour",
    "литератур",
    "literature",
    "вопрос",
    "question",
)


def _is_syllabus_related(text: str) -> bool:
    if not text:
        return False
    return any(hint in text for hint in _SYLLABUS_HINTS)

_DEFAULT_GUIDELINES = (
    "Рекомендации по заполнению силлабуса:\n"
    "1. Заполните код, название, семестр и академический год.\n"
    "2. Для каждой недели укажите тему, тип занятия и часы.\n"
    "3. Добавьте описание темы и цели (кратко, без лишней воды).\n"
    "4. Укажите основную и дополнительную литературу по каждой теме.\n"
    "5. Добавьте 2-4 контрольных вопроса по теме.\n"
    "6. Проверяйте, чтобы количество недель совпадало с планом.\n"
    "7. Используйте один язык заполнения без смешения.\n"
)


def _load_guidelines_from_txt(path: Path) -> str:
    for encoding in ("utf-8", "cp1251"):
        try:
            return path.read_text(encoding=encoding).strip()
        except Exception:
            continue
    return ""


def _extract_guidelines_from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(str(path))
    except Exception:
        return ""

    chunks = []
    total_len = 0
    for idx, page in enumerate(reader.pages):
        if idx >= _PDF_GUIDELINES_PAGES:
            break
        text = page.extract_text() or ""
        if text.strip():
            snippet = text.strip()
            chunks.append(snippet)
            total_len += len(snippet)
            if total_len >= _PDF_GUIDELINES_LIMIT:
                break

    joined = "\n".join(chunks)
    return joined[:_PDF_GUIDELINES_LIMIT]


def _trim_guidelines(text: str, limit: int = _GUIDELINES_LIMIT) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:limit]


def load_guidelines() -> str:
    global _GUIDELINES
    if _GUIDELINES is not None:
        return _GUIDELINES

    with _GUIDELINES_LOCK:
        if _GUIDELINES is not None:
            return _GUIDELINES

        root = Path(__file__).resolve().parents[1]
        txt_path = Path(os.getenv("SYLLABUS_GUIDELINES_PATH", root / "docs" / "syllabus_guidelines.txt"))
        pdf_path = Path(os.getenv("SYLLABUS_GUIDELINES_PDF", root / "Sillabus it sturtup.pdf"))

        guidelines = ""
        if txt_path.exists():
            guidelines = _load_guidelines_from_txt(txt_path)

        pdf_excerpt = ""
        if pdf_path.exists():
            pdf_excerpt = _extract_guidelines_from_pdf(pdf_path)

        if not guidelines and pdf_excerpt:
            guidelines = pdf_excerpt
        elif guidelines and pdf_excerpt:
            guidelines = f"{guidelines}\n\nПример оформления:\n{pdf_excerpt}"

        if not guidelines:
            guidelines = _DEFAULT_GUIDELINES
        else:
            guidelines = _trim_guidelines(guidelines)

        _GUIDELINES = guidelines
        return _GUIDELINES


def answer_syllabus_question(message: str, syllabus=None) -> tuple[str, str]:
    mode = _assistant_mode()
    fast = _fast_reply(message)
    if fast:
        return fast, "rules-only"

    if _is_fast_mode(mode):
        return _rules_only_answer(message), "rules-only"

    text_lower = message.strip().lower()
    is_syllabus = _is_syllabus_related(text_lower)
    guidelines = ""
    syllabus_text = ""

    if is_syllabus:
        guidelines = load_guidelines()
        if syllabus is not None:
            syllabus_text = build_syllabus_text(syllabus)[:_ASSISTANT_SYLLABUS_LIMIT]

        system = (
            "Ты помощник по заполнению силлабуса. "
            "Отвечай коротко и по делу на русском, предпочтительно списком. "
            "Если в вопросе не хватает данных, задай 1-2 уточняющих вопроса. "
            "Не придумывай факты и литературу."
        )

        prompt = (
            "<|im_start|>system\n"
            f"{system}\n\n"
            "Правила и пример оформления:\n"
            f"{guidelines}\n"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            f"Вопрос: {message}\n\n"
        )

        if syllabus_text:
            prompt += f"Текущие данные силлабуса:\n{syllabus_text}\n\n"
    else:
        system = (
            "Ты универсальный помощник. "
            "Отвечай кратко и по делу на русском. "
            "Если вопрос не ясен, задай один уточняющий вопрос."
        )
        prompt = (
            "<|im_start|>system\n"
            f"{system}\n"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            f"{message}\n"
        )

    prompt += "<|im_end|>\n<|im_start|>assistant\n"

    try:
        answer = generate_text(
            prompt,
            max_tokens=_ASSISTANT_MAX_TOKENS,
            temperature=0.2,
            top_p=0.9,
        )
        model_name = get_model_name()
    except Exception as exc:
        if mode == "auto" or _should_fallback(exc):
            return _rules_only_answer(message), "rules-only"
        return f"AI недоступен: {exc}", "rules-only"

    if not answer:
        answer = "Не получилось получить ответ. Попробуйте переформулировать вопрос."

    return answer.strip(), model_name
