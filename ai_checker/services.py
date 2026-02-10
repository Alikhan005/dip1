import json
import logging
import os
import re
from pathlib import Path

# --- ПРИОРИТЕТ 1: MarkItDown (Microsoft - Лучше для таблиц и DOCX) ---
try:
    from markitdown import MarkItDown
except ImportError:
    MarkItDown = None

# --- ПРИОРИТЕТ 2: pypdf (Запасной для PDF) ---
try:
    import pypdf
except ImportError:
    pypdf = None

from syllabi.models import Syllabus
from .llm import generate_text, get_model_name
from .models import AiCheckResult

logger = logging.getLogger(__name__)

# --- ОПТИМИЗАЦИЯ СКОРОСТИ ---
# Ограничиваем входной текст. 2500 символов (~600 токенов) достаточно для проверки структуры.
# Чем меньше текст, тем быстрее думает ИИ.
MAX_INPUT_CHARS = 2500 

def extract_text_from_file(file_path: str) -> str:
    """Извлекает текст. Приоритет: MarkItDown -> pypdf."""
    if not os.path.exists(file_path):
        return ""

    # 1. MarkItDown (Лучшее качество)
    if MarkItDown:
        try:
            md = MarkItDown()
            result = md.convert(file_path)
            if result.text_content and len(result.text_content) > 50:
                logger.info("✅ MarkItDown успешно прочитал файл")
                return result.text_content
        except Exception as e:
            logger.warning(f"⚠️ MarkItDown ошибка: {e}")

    # 2. pypdf (Запасной)
    if pypdf and file_path.lower().endswith('.pdf'):
        try:
            reader = pypdf.PdfReader(file_path)
            parts = []
            for page in reader.pages:
                txt = page.extract_text()
                if txt: parts.append(txt)
            text = "\n".join(parts)
            if len(text) > 50:
                logger.info("✅ pypdf успешно прочитал файл")
                return text
        except Exception as e:
            logger.warning(f"❌ pypdf ошибка: {e}")

    return ""

def build_syllabus_text_from_db(syllabus: Syllabus) -> str:
    parts = [f"Course: {syllabus.course.code}"]
    if syllabus.course_description:
        parts.append(f"Description: {syllabus.course_description}")
    
    topics = syllabus.syllabus_topics.filter(is_included=True).order_by("week_number")
    if topics.exists():
        parts.append("\nTopics:")
        for st in topics:
            parts.append(f"Week {st.week_number}: {st.get_title()}")
            if st.learning_outcomes:
                 parts.append(f"  - Outcome: {st.learning_outcomes}")
    
    return "\n".join(parts)

def _build_optimized_prompt(syllabus_text: str) -> str:
    """
    Короткий и четкий промпт для скорости.
    Заставляет ИИ отвечать JSON-ом без лишних размышлений.
    """
    return (
        "<|im_start|>system\n"
        "Ты эксперт Учебно-методического управления (УМУ). Твоя задача — проверить структуру силлабуса.\n"
        "Правила:\n"
        "1. Проверь наличие Целей, Тем (15 недель) и Литературы.\n"
        "2. Если темы не соответствуют целям — это ошибка.\n"
        "3. Если литературы нет или она старая (<2010) — это ошибка.\n"
        "Ответь СТРОГО в формате JSON: {\"approved\": boolean, \"feedback\": \"HTML text\"}.\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"Текст силлабуса (фрагмент):\n{syllabus_text}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )

def _parse_json_response(text: str) -> dict:
    """Пытается достать JSON из ответа, даже если ИИ добавил мусор."""
    cleaned = text.strip()
    # Убираем markdown ```json ... ```
    cleaned = re.sub(r"^```json", "", cleaned)
    cleaned = re.sub(r"^```", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned).strip()
    
    try:
        # Ищем фигурные скобки
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            json_str = cleaned[start : end + 1]
            return json.loads(json_str)
    except Exception:
        pass
    
    # Если JSON не распарсился, считаем это замечанием
    return {
        "approved": False, 
        "feedback": f"<h3>Результат анализа</h3><p>{cleaned[:500]}...</p>"
    }

def run_ai_check(syllabus: Syllabus) -> AiCheckResult:
    print(f"--- [DEBUG] Начало проверки силлабуса ID {syllabus.id} ---")
    
    content_source = "db"
    extracted_text = ""
    
    # 1. Читаем файл
    if syllabus.pdf_file:
        print(f"--- [DEBUG] Пробую читать файл: {syllabus.pdf_file.path} ---")
        extracted_text = extract_text_from_file(syllabus.pdf_file.path)
        if extracted_text:
            content_source = "file"
            print("--- [DEBUG] Текст успешно извлечен из файла ---")

    if content_source == "file":
        full_text = extracted_text
    else:
        print("--- [DEBUG] Беру текст из базы данных ---")
        full_text = build_syllabus_text_from_db(syllabus)

    # === УСКОРЕНИЕ 1: Обрезаем текст ===
    # Берем первые 2500 символов. Обычно ошибки в начале (цели) или в конце (литература).
    trimmed_text = full_text[:MAX_INPUT_CHARS]
    print(f"--- [DEBUG] Длина текста для ИИ: {len(trimmed_text)} символов ---")

    if len(trimmed_text) < 50:
         print("--- [DEBUG] Текст слишком короткий, отмена ---")
         return _save_check_result(syllabus, False, "<h3>Ошибка</h3><p>Файл пустой.</p>", "empty", "none")

    # 2. Генерируем ответ
    prompt = _build_optimized_prompt(trimmed_text)
    
    model_name = "unknown"
    raw_response = ""
    result_data = {}

    try:
        print("--- [DEBUG] Отправляю запрос в LLM... ---")
        
        # === УСКОРЕНИЕ 2: max_tokens=300 ===
        # Мы просим ИИ писать ОЧЕНЬ кратко. Это ускоряет генерацию в 2-3 раза.
        raw_response = generate_text(prompt, max_tokens=300, temperature=0.1)
        print("--- [DEBUG] Ответ от LLM получен! ---")
        
        model_name = get_model_name()
        result_data = _parse_json_response(raw_response)
        
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        print(f"--- [DEBUG] Ошибка LLM: {e} ---")
        result_data = {"approved": False, "feedback": f"Ошибка ИИ: {e}"}
        raw_response = str(e)

    print("--- [DEBUG] Сохраняю результат в БД ---")
    return _save_check_result(
        syllabus, 
        result_data.get("approved", False), 
        result_data.get("feedback", "Нет ответа"), 
        raw_response, 
        model_name
    )

def _save_check_result(syllabus, approved, feedback, raw_response, model_name):
    syllabus.ai_feedback = feedback
    
    # Делаем короткое саммари, очищая HTML теги
    clean_summary = re.sub(r'<[^>]+>', '', feedback)[:200] + "..."
    
    return AiCheckResult.objects.create(
        syllabus=syllabus,
        model_name=model_name,
        summary=clean_summary,
        raw_result={"approved": approved, "feedback": feedback, "full_response": raw_response}
    )