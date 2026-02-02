import json
import logging
import os
import re
from pathlib import Path

# --- ПРИОРИТЕТ 1: pypdf (Самый надежный) ---
try:
    import pypdf
except ImportError:
    pypdf = None

# --- ПРИОРИТЕТ 2: MarkItDown (Запасной) ---
try:
    from markitdown import MarkItDown
except ImportError:
    MarkItDown = None

from syllabi.models import Syllabus
from .llm import generate_text, get_model_name
from .models import AiCheckResult

logger = logging.getLogger(__name__)

# --- Загрузка переменных окружения ---
_ENV_LOADED = False
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED: return
    _ENV_LOADED = True
    if load_dotenv:
        root = Path(__file__).resolve().parents[1]
        env_path = root / ".env"
        if env_path.exists(): load_dotenv(env_path)

def _env_int(name: str, default: int) -> int:
    _ensure_env_loaded()
    try: return int(os.getenv(name, str(default)))
    except: return default


# --- ЧТЕНИЕ ФАЙЛА ---
def extract_text_from_file(file_path: str) -> str:
    """
    Извлекает текст. Сначала пробует pypdf.
    """
    if not os.path.exists(file_path):
        return ""

    extracted_text = ""

    # ПОПЫТКА 1: pypdf
    if pypdf and file_path.lower().endswith('.pdf'):
        try:
            reader = pypdf.PdfReader(file_path)
            parts = []
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    parts.append(txt)
            extracted_text = "\n".join(parts)
            
            if len(extracted_text) > 50:
                logger.info("Успешно прочитано через pypdf.")
                return extracted_text
        except Exception as e:
            logger.warning(f"pypdf ошибка: {e}")

    # ПОПЫТКА 2: MarkItDown
    if MarkItDown:
        try:
            md = MarkItDown()
            result = md.convert(file_path)
            text = result.text_content
            if text and len(text) > 50:
                return text
        except Exception as e:
            logger.warning(f"MarkItDown ошибка: {e}")

    return extracted_text


def build_syllabus_text_from_db(syllabus: Syllabus) -> str:
    parts = []
    parts.append(f"Course: {syllabus.course.code}")
    parts.append(f"Semester: {syllabus.semester}")
    parts.append(f"Description: {syllabus.course_description}")
    
    topics = syllabus.syllabus_topics.filter(is_included=True).order_by("week_number")
    if topics.exists():
        parts.append("\nTopics:")
        for st in topics:
            parts.append(f"Week {st.week_number}: {st.get_title()}")
    
    return "\n".join(parts)


def _build_hybrid_prompt(syllabus_text: str) -> str:
    """
    ГИБРИДНЫЙ ПРОМПТ.
    """
    system = (
        "Ты — Главный Методист Университета AlmaU. Твоя задача — проверить документ.\n"
        "ВАЖНО: Текст извлечен из PDF, он может быть склеен. Игнорируй мусор, ищи СМЫСЛ.\n\n"
        
        "ТВОИ ПРАВИЛА:\n"
        "1. ✅ СТРУКТУРА КУРСА:\n"
        "   - Ищи упоминания времени: 'Неделя 1', 'Week 5', '3-4 нед.', 'Модуль 1'.\n"
        "   - Если курс проектный (Startup, Capstone) — список из 15 лекций НЕ НУЖЕН. Достаточно этапов (MVP, CustDev, Защита).\n"
        "   - Диапазоны недель (3-4, 5-8) — это НОРМАЛЬНО.\n\n"
        
        "2. ✅ ОБЯЗАТЕЛЬНЫЕ БЛОКИ:\n"
        "   - Описание (Description/Objective).\n"
        "   - Оценивание/Политика (Grading/Policy).\n"
        "   - Расписание/Темы (Schedule/Topics).\n\n"
        
        "3. ❌ КОГДА ОТКЛОНЯТЬ:\n"
        "   - Только если файл пустой или это вообще не учебный план.\n\n"

        "ВЕРДИКТ:\n"
        "Если документ похож на реальный силлабус — ставь APPROVED: TRUE.\n"
        "В feedback пиши на русском языке."
    )
    
    format_instruction = (
        "ОТВЕТЬ ТОЛЬКО JSON-ОБЪЕКТОМ:\n"
        "{\n"
        "  \"approved\": true,\n"
        "  \"feedback\": \"Силлабус корректен.\"\n"
        "}"
    )

    return (
        "<|im_start|>system\n"
        f"{system}\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"Текст документа:\n================\n{syllabus_text}\n================\n\n{format_instruction}"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"```json", "", cleaned)
    cleaned = re.sub(r"```", "", cleaned).strip()
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start : end + 1])
    except Exception:
        pass
    lower_text = cleaned.lower()
    if "true" in lower_text and "approved" in lower_text:
        return {"approved": True, "feedback": cleaned[:200]}
    return {"approved": False, "feedback": "Не удалось прочитать ответ ИИ."}


def run_ai_check(syllabus: Syllabus) -> AiCheckResult:
    content_source = "db"
    extracted_text = ""
    
    # 1. Читаем файл
    if syllabus.pdf_file:
        extracted_text = extract_text_from_file(syllabus.pdf_file.path)
        if extracted_text and len(extracted_text) > 50:
            content_source = "file"
        else:
            logger.warning(f"Файл {syllabus.pk} не удалось прочитать.")

    if content_source == "file":
        syllabus_text = extracted_text
    else:
        syllabus_text = build_syllabus_text_from_db(syllabus)

    # !!! ВАЖНОЕ ИЗМЕНЕНИЕ: Урезаем до 6000 символов !!!
    # Это примерно 2000 токенов + системный промпт = ~2800 токенов. 
    # В память 4096 влезет с запасом.
    trimmed_text = syllabus_text[:6000]

    if len(trimmed_text) < 50:
        return _save_check_result(syllabus, False, "Файл пустой или текст не распознан.", "empty", "none")

    # 2. Проверка ИИ
    prompt = _build_hybrid_prompt(trimmed_text)
    
    model_name = "unknown"
    raw_response = ""
    result_data = {}

    try:
        logger.info(f"Checking Syllabus #{syllabus.id} (len={len(trimmed_text)} chars)...")
        # Генерируем ответ
        raw_response = generate_text(prompt, max_tokens=300, temperature=0.1)
        model_name = get_model_name()
        logger.info(f"AI Raw Response: {raw_response}")
        result_data = _parse_json_response(raw_response)
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        # Если даже так упадет, скажем пользователю
        feedback = "Ошибка: Файл слишком большой для ИИ. Попробуйте сжать PDF." if "context" in str(e).lower() else f"Ошибка ИИ: {e}"
        result_data = {"approved": False, "feedback": feedback}
        raw_response = str(e)

    return _save_check_result(
        syllabus, 
        result_data.get("approved", False), 
        result_data.get("feedback", "Нет комментария"), 
        raw_response, 
        model_name
    )


def _save_check_result(syllabus, approved, feedback, raw_response, model_name):
    syllabus.ai_feedback = feedback
    check_result = AiCheckResult.objects.create(
        syllabus=syllabus,
        model_name=model_name,
        summary=feedback[:500],
        raw_result={
            "approved": approved,
            "feedback": feedback,
            "full_response": raw_response
        }
    )
    return check_result