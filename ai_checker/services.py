import json
import os
import re
from pathlib import Path
from collections import Counter

from syllabi.models import Syllabus
from .llm import generate_text, get_model_name
from .models import AiCheckResult

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


def _pick_localized(lang: str, ru: str, kz: str, en: str) -> str:
    if lang == "kz":
        return kz or ru or en or ""
    if lang == "en":
        return en or ru or kz or ""
    return ru or en or kz or ""


def build_syllabus_text(syllabus: Syllabus) -> str:
    parts = []
    lang = syllabus.main_language

    parts.append(f"Course, {syllabus.course.code}")
    title = _pick_localized(
        lang,
        syllabus.course.title_ru,
        syllabus.course.title_kz,
        syllabus.course.title_en,
    )
    parts.append(f"Title, {title}")
    parts.append(f"Semester, {syllabus.semester}")
    parts.append("")

    topics = (
        syllabus.syllabus_topics.select_related("topic")
        .prefetch_related("topic__literature", "topic__questions")
        .order_by("week_number")
    )

    for st in topics:
        t = st.topic
        title = st.get_title()
        parts.append(f"Week {st.week_number}, {title}")
        description = _pick_localized(lang, t.description_ru, t.description_kz, t.description_en)
        if description:
            parts.append(f"Description, {description[:300]}")
        lits = list(t.literature.all())
        if lits:
            lits = [lit.title for lit in lits]
            parts.append("Literature, " + "; ".join(lits))
        qs = list(t.questions.all())
        if qs:
            qs = [_pick_localized(lang, q.question_ru, q.question_kz, q.question_en) for q in qs]
            parts.append("Questions, " + "; ".join(qs[:3]))
        parts.append("")

    return "\n".join(parts)


def analyze_structure(syllabus: Syllabus) -> dict:
    topics = (
        syllabus.syllabus_topics.select_related("topic")
        .prefetch_related("topic__literature", "topic__questions")
        .order_by("week_number")
    )
    total_topics = topics.count()
    weeks = [st.week_number for st in topics]
    unique_weeks = sorted(set(weeks)) if weeks else []
    week_counter = Counter(weeks)
    duplicate_weeks = sum(1 for count in week_counter.values() if count > 1)

    no_lit = 0
    no_questions = 0

    for st in topics:
        t = st.topic
        if not t.literature.all():
            no_lit += 1
        if not t.questions.all():
            no_questions += 1

    issues = []

    if total_topics == 0:
        issues.append("В силлабусе нет тем.")

    if syllabus.total_weeks and unique_weeks:
        if max(unique_weeks) < syllabus.total_weeks:
            issues.append(
                f"Покрыты не все недели: заполнено {max(unique_weeks)}, по плану {syllabus.total_weeks}."
            )
        if max(unique_weeks) > syllabus.total_weeks:
            issues.append(
                f"Есть темы вне планового количества недель: заполнено {max(unique_weeks)}, "
                f"по плану {syllabus.total_weeks}."
            )

    if no_lit:
        issues.append(f"У {no_lit} тем нет привязанной литературы.")

    if no_questions:
        issues.append(f"У {no_questions} тем нет контрольных вопросов.")

    if duplicate_weeks:
        issues.append("Есть дублирование номеров недель.")

    return {
        "total_topics": total_topics,
        "weeks_covered": unique_weeks,
        "topics_without_literature": no_lit,
        "topics_without_questions": no_questions,
        "duplicate_weeks": duplicate_weeks,
        "issues": issues,
    }


def _build_llm_prompt(syllabus_text: str) -> str:
    system = (
        "You check a university syllabus for structure and completeness. "
        "Do not invent facts or literature. "
        "Return ONLY valid JSON with the schema below. "
        "Write the summary and issues in Russian."
    )

    schema = (
        "{\n"
        '  "summary": "2-4 sentences",\n'
        '  "issues": [\n'
        '    {"severity": "low|medium|high", "where": "...", "message": "...", "fix": "..."}\n'
        "  ],\n"
        '  "checks": {\n'
        '    "weeks_ok": true,\n'
        '    "hours_ok": true,\n'
        '    "literature_ok": true,\n'
        '    "questions_ok": true,\n'
        '    "language_mix": true\n'
        "  }\n"
        "}"
    )

    return (
        "<|im_start|>system\n"
        f"{system}\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        "Check the syllabus text and return JSON only.\n\n"
        "JSON schema:\n"
        f"{schema}\n\n"
        f"Syllabus text:\n{syllabus_text}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def _parse_llm_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM did not return a JSON object.")

    snippet = cleaned[start : end + 1]
    return json.loads(snippet)


def _format_llm_issues(issues: list) -> str:
    lines = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "")).strip()
        where = str(item.get("where", "")).strip()
        message = str(item.get("message", "")).strip()
        fix = str(item.get("fix", "")).strip()

        if not (severity or where or message or fix):
            continue

        line = "- "
        if severity:
            line += f"[{severity}] "
        if where:
            line += f"{where}: "
        line += message
        if fix:
            line += f" Исправление: {fix}"
        lines.append(line.strip())

    return "\n".join(lines)


def _build_summary_text(llm_result: dict, struct: dict, syllabus: Syllabus) -> str:
    parts = []

    if isinstance(llm_result, dict):
        summary = llm_result.get("summary")
        if isinstance(summary, str) and summary.strip():
            parts.append(summary.strip())

        issues = llm_result.get("issues")
        if isinstance(issues, list) and issues:
            formatted = _format_llm_issues(issues)
            if formatted:
                parts.append("Проблемы:\n" + formatted)

    if not parts:
        total_topics = syllabus.syllabus_topics.count()
        total_weeks = syllabus.total_weeks or 0
        parts.append(
            f"Силлабус по курсу {syllabus.course.display_title} содержит {total_topics} "
            f"тем(ы) на {total_weeks} недель."
        )

    if struct.get("issues"):
        parts.append("Структурные проблемы:\n" + "\n".join(f"- {i}" for i in struct["issues"]))
    else:
        parts.append("Структурная проверка: проблем не найдено.")

    return "\n\n".join(parts)


def run_ai_check(syllabus: Syllabus) -> AiCheckResult:
    base_text = build_syllabus_text(syllabus)
    text_limit = _env_int("LLM_CHECK_TEXT_LIMIT", 5000)
    max_tokens = _env_int("LLM_CHECK_MAX_TOKENS", 450)
    trimmed = base_text[:text_limit]

    struct = analyze_structure(syllabus)

    llm_text = ""
    llm_result = {}
    model_name = "rules-only"

    try:
        prompt = _build_llm_prompt(trimmed)
        llm_text = generate_text(prompt, max_tokens=max_tokens)
        llm_result = _parse_llm_json(llm_text)
        model_name = get_model_name()
    except Exception as exc:
        llm_result = {"error": str(exc)}

    final_summary = _build_summary_text(llm_result, struct, syllabus)

    return AiCheckResult.objects.create(
        syllabus=syllabus,
        model_name=model_name,
        summary=final_summary,
        raw_result={"llm": llm_result, "llm_text": llm_text, "structure": struct},
    )
