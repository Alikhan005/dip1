# Структура проекта и ER-диаграмма

Эта справка описывает основные сущности проекта и то, как они связаны.

## 1) Сущности и связи

Основные таблицы:

- USER (`accounts.User`)
  - роли: teacher, program_leader, dean, umu, admin
- COURSE (`catalog.Course`)
  - владелец курса: `owner_id -> USER`
  - флаг `is_shared` для общих курсов
- TOPIC (`catalog.Topic`)
  - принадлежит курсу: `course_id -> COURSE`
- TOPIC_LITERATURE (`catalog.TopicLiterature`)
  - принадлежит теме: `topic_id -> TOPIC`
- TOPIC_QUESTION (`catalog.TopicQuestion`)
  - принадлежит теме: `topic_id -> TOPIC`
- SYLLABUS (`syllabi.Syllabus`)
  - принадлежит курсу: `course_id -> COURSE`
  - создатель: `creator_id -> USER`
  - флаг `is_shared` для общего доступа
- SYLLABUS_TOPIC (`syllabi.SyllabusTopic`)
  - связывает силлабус и тему: `syllabus_id -> SYLLABUS`, `topic_id -> TOPIC`
  - хранит параметры недели, часов, кастомного названия
- SYLLABUS_STATUS_LOG (`workflow.SyllabusStatusLog`)
  - история статусов: `syllabus_id -> SYLLABUS`, `changed_by_id -> USER`
- AI_CHECK_RESULT (`ai_checker.AiCheckResult`)
  - результаты AI-проверки: `syllabus_id -> SYLLABUS`

Кардинальности:

- USER 1-M COURSE
- USER 1-M SYLLABUS
- USER 1-M SYLLABUS_STATUS_LOG
- COURSE 1-M TOPIC
- COURSE 1-M SYLLABUS
- TOPIC 1-M TOPIC_LITERATURE
- TOPIC 1-M TOPIC_QUESTION
- SYLLABUS 1-M SYLLABUS_TOPIC
- TOPIC 1-M SYLLABUS_TOPIC
- SYLLABUS 1-M AI_CHECK_RESULT
- SYLLABUS 1-M SYLLABUS_STATUS_LOG

ER-диаграмма (Mermaid) находится в `docs/er.mmd`.

## 2) Основной поток работы

1. Преподаватель создаёт `Course`.
2. Внутри курса создаёт `Topic`, добавляет литературу и контрольные вопросы.
3. Создаёт `Syllabus` (семестр, учебный год, язык, недели).
4. Заполняет структуру силлабуса через `SyllabusTopic`
   (какая тема на какой неделе, часы, кастомные названия).
5. Согласование меняет `Syllabus.status`, а каждый шаг фиксируется в `SyllabusStatusLog`.

## 3) AI-проверка и помощник

- AI‑проверка создаёт `AiCheckResult` и сохраняет summary + raw_result JSON.
- Чат‑помощник отвечает на вопросы преподавателя:
  - режим `fast` — мгновенно (rules‑only),
  - режим `llm` — медленнее, но «умнее».
  - режим переключается через `LLM_ASSISTANT_MODE` в `.env`.

## 4) Общие (shared) сущности

- `Course.is_shared` и `Syllabus.is_shared` дают возможность делиться
  материалами с другими преподавателями.
*** End Patch"})}from functions.apply_patch to=functions.apply_patch.commentary ็ตทรู code```payload={"patch":"*** Begin Patch\n*** Add File: almau-syllabus/docs/er.md\n+# Структура проекта и ER‑диаграмма\n+\n+Эта справка описывает основные сущности проекта и то, как они связаны.\n+\n+## 1) Сущности и связи\n+\n+Основные таблицы:\n+\n+- USER (`accounts.User`)\n+  - роли: teacher, program_leader, dean, umu, admin\n+- COURSE (`catalog.Course`)\n+  - владелец курса: `owner_id → USER`\n+  - флаг `is_shared` для общих курсов\n+- TOPIC (`catalog.Topic`)\n+  - принадлежит курсу: `course_id → COURSE`\n+- TOPIC_LITERATURE (`catalog.TopicLiterature`)\n+  - принадлежит теме: `topic_id → TOPIC`\n+- TOPIC_QUESTION (`catalog.TopicQuestion`)\n+  - принадлежит теме: `topic_id → TOPIC`\n+- SYLLABUS (`syllabi.Syllabus`)\n+  - принадлежит курсу: `course_id → COURSE`\n+  - создатель: `creator_id → USER`\n+  - флаг `is_shared` для общего доступа\n+- SYLLABUS_TOPIC (`syllabi.SyllabusTopic`)\n+  - связывает силлабус и тему: `syllabus_id → SYLLABUS`, `topic_id → TOPIC`\n+  - хранит параметры недели, часов, кастомного названия\n+- SYLLABUS_STATUS_LOG (`workflow.SyllabusStatusLog`)\n+  - история статусов: `syllabus_id → SYLLABUS`, `changed_by_id → USER`\n+- AI_CHECK_RESULT (`ai_checker.AiCheckResult`)\n+  - результаты AI‑проверки: `syllabus_id → SYLLABUS`\n+\n+Кардинальности:\n+\n+- USER 1—M COURSE\n+- USER 1—M SYLLABUS\n+- USER 1—M SYLLABUS_STATUS_LOG\n+- COURSE 1—M TOPIC\n+- COURSE 1—M SYLLABUS\n+- TOPIC 1—M TOPIC_LITERATURE\n+- TOPIC 1—M TOPIC_QUESTION\n+- SYLLABUS 1—M SYLLABUS_TOPIC\n+- TOPIC 1—M SYLLABUS_TOPIC\n+- SYLLABUS 1—M AI_CHECK_RESULT\n+- SYLLABUS 1—M SYLLABUS_STATUS_LOG\n+\n+ER‑диаграмма (Mermaid) находится в `docs/er.mmd`.\n+\n+## 2) Основной поток работы\n+\n+1. Преподаватель создаёт `Course`.\n+2. Внутри курса создаёт `Topic`, добавляет литературу и контрольные вопросы.\n+3. Создаёт `Syllabus` (семестр, учебный год, язык, недели).\n+4. Заполняет структуру силлабуса через `SyllabusTopic`\n+   (какая тема на какой неделе, часы, кастомные названия).\n+5. Согласование меняет `Syllabus.status`, а каждый шаг фиксируется в `SyllabusStatusLog`.\n+\n+## 3) AI‑проверка и помощник\n+\n+- AI‑проверка создаёт `AiCheckResult` и сохраняет summary + raw_result JSON.\n+- Чат‑помощник отвечает на вопросы преподавателя:\n+  - режим `fast` — мгновенно (rules‑only),\n+  - режим `llm` — медленнее, но «умнее».\n+  - режим переключается через `LLM_ASSISTANT_MODE` в `.env`.\n+\n+## 4) Общие (shared) сущности\n+\n+- `Course.is_shared` и `Syllabus.is_shared` дают возможность делиться\n+  материалами с другими преподавателями.\n*** End Patch"}>``` 
