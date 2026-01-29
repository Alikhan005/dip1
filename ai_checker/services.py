import json
import logging
import os
import re
from pathlib import Path
from collections import Counter

# Импорт библиотеки от Microsoft для чтения файлов
try:
    from markitdown import MarkItDown
except ImportError:
    MarkItDown = None

from syllabi.models import Syllabus
from .llm import generate_text, get_model_name
from .models import AiCheckResult

logger = logging.getLogger(__name__)

_ENV_LOADED = False

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
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


def extract_text_from_file(file_path: str) -> str:
    """
    Использует MarkItDown для извлечения текста из PDF/DOCX.
    """
    if not MarkItDown:
        logger.warning("Библиотека markitdown не установлена. Чтение файлов недоступно.")
        return ""
        
    if not os.path.exists(file_path):
        return ""
    
    try:
        md = MarkItDown()
        result = md.convert(file_path)
        return result.text_content
    except Exception as e:
        logger.error(f"Ошибка чтения файла {file_path}: {e}")
        return ""


def build_syllabus_text_from_db(syllabus: Syllabus) -> str:
    """Собирает текст из полей базы данных (если файла нет)."""
    parts = []
    lang = syllabus.main_language

    parts.append(f"Course: {syllabus.course.code} - {syllabus.course.title_ru}")
    parts.append(f"Semester: {syllabus.semester}")
    parts.append(f"Description: {syllabus.course_description}")
    parts.append(f"Policy: {syllabus.course_policy}")
    parts.append("")
    parts.append("Topics Structure:")

    topics = syllabus.syllabus_topics.filter(is_included=True).order_by("week_number")
    
    weeks = []
    for st in topics:
        weeks.append(st.week_number)
        title = st.get_title()
        parts.append(f"Week {st.week_number}: {title}")
        
        # Литература темы
        lits = [lit.title for lit in st.topic.literature.all()]
        if lits:
            parts.append(f"  Literature: {', '.join(lits)}")

    if not weeks:
        parts.append("(Topics list is empty)")

    return "\n".join(parts)


def _build_strict_prompt(syllabus_text: str) -> str:
    """
    Создает промпт для Роли 'Строгий Методист'.
    """
    system = (
        "Ты строгий методист университета AlmaU. Твоя задача — проверить текст силлабуса.\n"
        "Критерии проверки:\n"
        "1. Актуальность литературы: источники не должны быть старше 10 лет.\n"
        "2. Структура курса: должно быть расписано ровно 15 недель занятий.\n"
        "3. Полнота: должны присутствовать разделы 'Описание курса' и 'Политика оценивания'.\n"
        "4. Стиль: текст должен быть написан академическим языком.\n\n"
        "Ответь ИСКЛЮЧИТЕЛЬНО в формате JSON следующего вида:\n"
        "{\n"
        "  \"approved\": true или false,\n"
        "  \"feedback\": \"Краткое резюме ошибок на русском языке. Если все хорошо — напиши 'Силлабус соответствует стандартам'.\"\n"
        "}"
    )

    return (
        "<|im_start|>system\n"
        f"{system}\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"Вот текст силлабуса для проверки:\n\n{syllabus_text}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def _parse_strict_json(text: str) -> dict:
    """Парсит ответ ИИ, очищая от Markdown."""
    cleaned = text.strip()
    # Убираем ```json ... ```
    if "```" in cleaned:
        cleaned = re.sub(r"```(?:json)?", "", cleaned).strip()
    
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            snippet = cleaned[start : end + 1]
            return json.loads(snippet)
    except Exception:
        pass
    
    # Если JSON сломан, возвращаем ошибку
    return {
        "approved": False,
        "feedback": f"Ошибка чтения ответа от ИИ. Сырой ответ: {text[:100]}..."
    }


def run_ai_check(syllabus: Syllabus) -> AiCheckResult:
    """
    Основная функция проверки.
    1. Извлекает текст (из файла или БД).
    2. Отправляет ИИ.
    3. Сохраняет результат.
    """
    
    # 1. Получаем текст
    content_source = "db"
    if syllabus.pdf_file:
        try:
            file_path = syllabus.pdf_file.path
            extracted_text = extract_text_from_file(file_path)
            if extracted_text and len(extracted_text) > 50:
                syllabus_text = f"=== TEXT FROM UPLOADED FILE ===\n{extracted_text}"
                content_source = "file"
            else:
                syllabus_text = build_syllabus_text_from_db(syllabus)
                logger.warning(f"Файл пуст или не прочитан, используем БД для {syllabus.id}")
        except Exception as e:
            logger.error(f"Ошибка доступа к файлу: {e}")
            syllabus_text = build_syllabus_text_from_db(syllabus)
    else:
        syllabus_text = build_syllabus_text_from_db(syllabus)

    # Обрезаем, если слишком много (для экономии токенов и скорости)
    # Qwen 2.5 кушает много, но для диплома лучше ограничить разумно
    text_limit = _env_int("LLM_CHECK_TEXT_LIMIT", 10000)
    trimmed_text = syllabus_text[:text_limit]

    # 2. Формируем запрос
    prompt = _build_strict_prompt(trimmed_text)
    max_tokens = _env_int("LLM_CHECK_MAX_TOKENS", 500)

    model_name = "unknown"
    llm_result = {}
    raw_response = ""

    try:
        # 3. Генерация
        logger.info(f"Запуск AI проверки (source={content_source}) для Syllabus #{syllabus.id}")
        
        raw_response = generate_text(prompt, max_tokens=max_tokens, temperature=0.1)
        model_name = get_model_name()
        
        # ЛОГИРОВАНИЕ (Требование Тимура: видеть, что ответил ИИ)
        logger.info(f"AI Raw Response: {raw_response}")

        # 4. Парсинг
        llm_result = _parse_strict_json(raw_response)

    except Exception as exc:
        logger.error(f"AI Generation failed: {exc}")
        llm_result = {"approved": False, "feedback": f"Technical Error: {str(exc)}"}
        raw_response = str(exc)

    # 5. Сохранение результата
    # Обновляем сам силлабус (записываем фидбек)
    syllabus.ai_feedback = llm_result.get("feedback", "")
    
    # Если проверка пройдена -> статус меняем снаружи (в воркере), 
    # но результат возвращаем честный.
    
    # Сохраняем историю проверок (AiCheckResult)
    check_result = AiCheckResult.objects.create(
        syllabus=syllabus,
        model_name=model_name,
        summary=llm_result.get("feedback", ""),
        raw_result={
            "approved": llm_result.get("approved", False),
            "source": content_source,
            "full_response": raw_response
        },
    )
    
    return check_result