import os
import re
import threading
from pathlib import Path

# ИСПРАВЛЕНИЕ: Импортируем новые функции из services
from .llm import generate_text, get_model_name
from .services import build_syllabus_text_from_db, extract_text_from_file

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
_TRANSLATION_TEXT_LIMIT = _env_int("LLM_TRANSLATION_TEXT_LIMIT", 1200)
_TRANSLATION_MAX_TOKENS = _env_int("LLM_TRANSLATION_MAX_TOKENS", 400)

_GREETING_CLEAN_RE = re.compile(r"[^\w\s\-]+", re.UNICODE)
_FAST_GREETINGS = {
    "привет",
    "здравствуйте",
    "добрый день",
    "добрый вечер",
    "доброе утро",
    "hi",
    "hello",
}

_TRANSLATION_KEYWORDS = (
    "переведи",
    "перевод",
    "перевести",
    "translate",
    "translation",
)

_TRANSLATION_TARGETS = {
    "ru": ("ru", "рус", "russian"),
    "kz": ("kz", "каз", "қаз", "kazakh", "kaz"),
    "en": ("en", "англ", "english"),
}


def _fast_reply(message: str) -> str | None:
    cleaned = _GREETING_CLEAN_RE.sub("", message).strip().lower()
    if cleaned in _FAST_GREETINGS:
        return (
            "Здравствуйте! Помогу с темами, неделями, часами, литературой и "
            "структурой силлабуса. Чем могу помочь?"
        )
    return None


def _detect_translation_targets(text: str) -> list[str]:
    lowered = text.lower()
    if "3 языка" in lowered or "три языка" in lowered or "на три" in lowered or "на 3" in lowered:
        return ["ru", "kz", "en"]

    targets = []
    for code, keywords in _TRANSLATION_TARGETS.items():
        if any(keyword in lowered for keyword in keywords):
            targets.append(code)

    return targets or ["ru", "kz", "en"]


def _extract_translation_text(message: str) -> str:
    for open_char, close_char in (("«", "»"), ('"', '"'), ("'", "'")):
        start = message.find(open_char)
        if start != -1:
            end = message.find(close_char, start + 1)
            if end != -1:
                return message[start + 1 : end].strip()

    for separator in (":", "—", "–", "\n"):
        if separator in message:
            return message.split(separator, 1)[1].strip()

    return ""


def _translation_request(message: str) -> dict | None:
    lowered = message.lower()
    if not any(keyword in lowered for keyword in _TRANSLATION_KEYWORDS):
        return None
    return {
        "text": _extract_translation_text(message),
        "targets": _detect_translation_targets(lowered),
    }


def _build_translation_prompt(text: str, targets: list[str]) -> str:
    language_labels = {"ru": "Russian", "kz": "Kazakh", "en": "English"}
    ordered_targets = [code for code in ("ru", "kz", "en") if code in targets]
    target_list = ", ".join(language_labels[code] for code in ordered_targets)
    output_format = "\n".join(f"{code.upper()}: ..." for code in ordered_targets)

    system = (
        "You are a professional translator for university syllabi. "
        "Translate the user text into the requested languages. "
        "Preserve meaning, tone, and formatting. Do not add new content."
    )

    return (
        "<|im_start|>system\n"
        f"{system}\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"Target languages: {target_list}.\n\n"
        "Return ONLY the translations in the format below:\n"
        f"{output_format}\n\n"
        f"Text:\n{text}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _app_help_answer(message: str) -> str | None:
    text = message.strip().lower()
    if not text:
        return None

    if _contains_any(
        text,
        (
            "общий доступ",
            "общим",
            "общий",
            "поделиться",
            "share",
            "shared",
            "публич",
            "опубликовать",
        ),
    ) and _contains_any(text, ("силлабус", "syllabus", "файл", "pdf")):
        return (
            "Чтобы открыть общий доступ к силлабусу:\n"
            "1) Откройте нужный силлабус.\n"
            "2) Нажмите кнопку \"Сделать общим/Открыть общий доступ\".\n"
            "3) После этого он появится в разделе \"Общие силлабусы\".\n"
            "Если кнопки нет — нужны права автора или администратора.\n"
            "Готовый PDF можно прикрепить в блоке \"Учебный файл\"."
        )

    if _contains_any(text, ("скач", "выгруз", "экспорт", "download")) and _contains_any(
        text, ("pdf", "силлабус", "syllabus")
    ):
        return "Скачать PDF можно со страницы силлабуса кнопкой \"Скачать PDF\"."

    if _contains_any(text, ("загруз", "прикреп", "влож", "обнов", "upload", "attach")) and _contains_any(
        text, ("pdf", "файл", "силлабус", "syllabus")
    ):
        return (
            "Чтобы прикрепить или обновить PDF:\n"
            "1) Откройте силлабус.\n"
            "2) В блоке \"Учебный файл\" выберите PDF и нажмите \"Загрузить/обновить\".\n"
            "Право есть у автора/админа (или у УМУ для утвержденного)."
        )

    if _contains_any(text, ("создать", "новый", "добав", "оформить")) and _contains_any(
        text, ("силлабус", "syllabus")
    ):
        return (
            "Создать силлабус:\n"
            "1) Силлабусы -> \"Создать\".\n"
            "2) Заполните базовые поля.\n"
            "3) Можно выбрать \"Скопировать из\" или галочку \"Заполнить темы из курса\".\n"
            "4) При необходимости прикрепите PDF.\n"
            "5) Далее заполните разделы и темы."
        )

    if _contains_any(text, ("копир", "дубликат", "шаблон", "перенести", "импорт")) and _contains_any(
        text, ("силлабус", "syllabus")
    ):
        return (
            "Быстрый перенос/копия силлабуса:\n"
            "- На форме создания есть поле \"Скопировать из\".\n"
            "- Выберите существующий силлабус своего курса и создайте новый.\n"
            "- Дальше правьте разделы и темы."
        )

    if _contains_any(text, ("общие", "shared")) and _contains_any(text, ("силлабус", "syllabus")):
        return "Раздел \"Общие силлабусы\" находится в верхнем меню."

    if _contains_any(text, ("общие", "shared")) and _contains_any(text, ("курс", "course")):
        return "Раздел \"Общие курсы\" находится в верхнем меню."

    if _contains_any(text, ("ai", "ии")) and _contains_any(text, ("провер", "check", "анализ")):
        return "AI-проверка запускается на странице силлабуса кнопкой \"Запустить AI-проверку\"."

    if _contains_any(text, ("ai", "ии")) and _contains_any(text, ("заполн", "черновик", "draft", "авто")):
        return "Автозаполнение отключено: силлабус собирается вручную из банка тем."

    if _contains_any(
        text,
        ("ник", "никнейм", "логин", "username", "имя пользователя", "профиль", "email", "почт"),
    ):
        return (
            "Профиль открывается в верхнем меню \"Профиль\". Там можно изменить имя, "
            "фамилию, email, факультет и кафедру и нажать \"Сохранить\". "
            "Имя пользователя (логин) не редактируется — для смены нужен администратор."
        )

    if _contains_any(text, ("редакт", "измен", "править", "edit")) and _contains_any(
        text, ("тем", "раздел", "силлабус", "syllabus")
    ):
        return (
            "Редактирование силлабуса:\n"
            "- Откройте силлабус.\n"
            "- Используйте кнопки \"Редактировать разделы\" или \"Редактировать темы\"."
        )

    return None


def _rules_only_answer(message: str) -> str:
    text = message.strip().lower()
    if not text:
        return (
            "Напишите вопрос по силлабусу. Например: "
            "\"Сколько недель?\", \"Предложи темы\", \"Подбери литературу\"."
        )

    if any(keyword in text for keyword in _TRANSLATION_KEYWORDS):
        return (
            "AI-перевод доступен при включенном LLM. "
            "Пришлите текст в кавычках или после двоеточия, например: "
            "\"Переведи на 3 языка: ...\"."
        )

    if "силлабус" in text and any(
        word in text for word in ("цель", "компетенц", "обуч", "результат", "программ")
    ):
        return (
            "Короткий шаблон силлабуса:\n"
            "1) Данные курса: код, название, семестр, язык.\n"
            "2) Цели и результаты обучения (глаголы действия).\n"
            "3) Темы по неделям + формат (лекция/практика/лаб) + часы.\n"
            "4) Оценивание: виды работ и проценты.\n"
            "5) Литература: основная 2-3, дополнительная 2-5."
        )

    if "недел" in text or "week" in text:
        return (
            "Сформируйте план по неделям: неделя, тема, тип занятия, часы и задания. "
            "Количество недель должно совпадать с учебным планом."
        )

    if "час" in text or "hour" in text:
        return (
            "Укажите аудиторные часы и СРС/СРО. Распределите их по темам и "
            "проверьте итоговую сумму по плану."
        )

    if "литератур" in text or "literatur" in text:
        return (
            "Обычно: 2-3 источника в основной литературе и 2-5 в дополнительной. "
            "Укажите автора, название, год и издательство (или ссылку)."
        )

    if "вопрос" in text or "question" in text:
        return (
            "Добавьте 2-4 контрольных вопроса или задания на тему, "
            "чтобы проверить понимание и применение материала."
        )

    if "тема" in text or "topic" in text:
        return (
            "Список тем делайте логичным и последовательным, от базовых к продвинутым. "
            "Для каждой темы добавьте краткое описание и ожидаемый результат."
        )

    return (
        "Могу помочь с работой в системе: общий доступ, загрузка/скачивание PDF, "
        "создание или копирование силлабуса, проверка структуры (AI). "
        "Опишите задачу, и я дам короткие шаги."
    )


_SYLLABUS_HINTS = (
    "силлабус",
    "syllabus",
    "курс",
    "course",
    "тема",
    "темы",
    "topic",
    "неделя",
    "недели",
    "week",
    "часы",
    "hour",
    "литератур",
    "literature",
    "вопрос",
    "question",
    "оцениван",
    "assessment",
    "общий",
    "доступ",
    "поделиться",
    "файл",
    "pdf",
    "загруз",
    "скач",
    "создать",
    "копир",
    "ai",
    "ии",
)


def _is_syllabus_related(text: str) -> bool:
    if not text:
        return False
    return any(hint in text for hint in _SYLLABUS_HINTS)


_DEFAULT_GUIDELINES = (
    "Рекомендации по заполнению силлабуса:\n"
    "1. Укажите цель курса и результаты обучения.\n"
    "2. Распишите темы по неделям, укажите формат и часы.\n"
    "3. Для каждой темы добавьте краткое описание и задания.\n"
    "4. Литература: основная 2-3, дополнительная 2-5 источников.\n"
    "5. Опишите оценивание: виды работ, проценты, критерии.\n"
    "6. Добавьте политики курса (посещаемость, дедлайны, академическая честность).\n"
    "7. Проверьте согласованность количества недель и часов с учебным планом.\n"
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
            guidelines = f"{guidelines}\n\nКраткий фрагмент из PDF:\n{pdf_excerpt}"

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

    app_help = _app_help_answer(message)
    if app_help:
        return app_help, "rules-only"

    translation = _translation_request(message)
    if translation is not None:
        text = (translation.get("text") or "").strip()
        targets = translation.get("targets") or ["ru", "kz", "en"]
        if not text:
            return (
                "Пришлите текст для перевода в кавычках или после двоеточия, "
                'например: "Переведи на 3 языка: ...".',
                "rules-only",
            )
        if len(text) > _TRANSLATION_TEXT_LIMIT:
            return (
                "Текст слишком длинный для перевода. Отправьте более короткий фрагмент.",
                "rules-only",
            )
        if _is_fast_mode(mode):
            return (
                "AI-перевод доступен в режиме auto/llm. Включите LLM и повторите запрос.",
                "rules-only",
            )

        prompt = _build_translation_prompt(text, targets)
        try:
            answer = generate_text(
                prompt,
                max_tokens=_TRANSLATION_MAX_TOKENS,
                temperature=0.2,
                top_p=0.9,
            )
            model_name = get_model_name()
        except Exception as exc:
            if mode == "auto" or _should_fallback(exc):
                return (
                    "AI-перевод недоступен. Проверьте настройки LLM и повторите запрос.",
                    "rules-only",
                )
            return f"AI недоступен: {exc}", "rules-only"

        if not answer:
            return (
                "Не удалось получить перевод. Попробуйте еще раз или сократите текст.",
                "rules-only",
            )
        return answer.strip(), model_name

    if _is_fast_mode(mode):
        return _rules_only_answer(message), "rules-only"

    text_lower = message.strip().lower()
    is_syllabus = _is_syllabus_related(text_lower)
    guidelines = ""
    syllabus_text = ""

    if is_syllabus:
        guidelines = load_guidelines()
        if syllabus is not None:
            # ИСПРАВЛЕНИЕ: Используем правильное имя функции
            # Пытаемся получить текст из PDF, если он есть, иначе из БД
            extracted = None
            if syllabus.pdf_file:
                try:
                    extracted = extract_text_from_file(syllabus.pdf_file.path)
                except Exception:
                    pass
            
            if extracted and len(extracted) > 50:
                 syllabus_text = f"CONTENT FROM FILE:\n{extracted[:_ASSISTANT_SYLLABUS_LIMIT]}"
            else:
                 syllabus_text = build_syllabus_text_from_db(syllabus)[:_ASSISTANT_SYLLABUS_LIMIT]

        system = (
            "Ты помощник по составлению университетского силлабуса. "
            "Отвечай кратко и по делу, на русском. "
            "Не выдумывай факты, если их нет в данных. "
            "Если не хватает деталей, задай 1-2 уточняющих вопроса. "
            "Если просят пример, дай короткий пример."
        )

        prompt = (
            "<|im_start|>system\n"
            f"{system}\n\n"
            "Рекомендации по заполнению:\n"
            f"{guidelines}\n"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            f"Вопрос: {message}\n\n"
        )

        if syllabus_text:
            prompt += f"Контекст силлабуса:\n{syllabus_text}\n\n"
    else:
        system = (
            "Ты универсальный помощник. "
            "Отвечай максимально кратко и понятно на русском: 1-2 предложения. "
            "Если нужны шаги, дай не больше 3 пунктов. "
            "Если вопрос про работу в системе, дай короткие шаги. "
            "Если не хватает данных, задай 1 уточняющий вопрос."
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
        answer = "Не удалось получить ответ. Попробуйте переформулировать вопрос."

    return answer.strip(), model_name