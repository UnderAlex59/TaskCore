# План экспериментальной проверки гипотез H1-H5

Документ фиксирует воспроизводимую методику оценки MVP на размеченных
синтетических данных. Эксперимент не доказывает промышленное снижение нагрузки
в реальной команде напрямую; он проверяет измеримые свойства прототипа:
выявление дефектов требований, использование проектного контекста, ответы по
RAG-памяти, формализацию предложений изменений из коммуникации и способность
системы адаптировать проверку новых задач к накопленному проектному опыту.

## Общий порядок эксперимента

1. Зафиксировать версию приложения, LLM-провайдера, модель, prompt-версии и
   параметры запуска.
2. Подготовить синтетические, но реалистичные наборы задач по предметной
   области: документы, импорты, статусы, уведомления, роли, отчеты.
3. Для каждого кейса заранее задать эталонную разметку: verdict, дефекты,
   уточняющие вопросы, релевантные источники, ожидаемые ответы и предложения
   изменений.
4. Запустить eval-инструменты системы на одинаковой конфигурации.
5. Сравнить summary metrics с порогами гипотез.
6. Выполнить анализ ошибок: ложные замечания, пропущенные дефекты,
   нерелевантные источники, галлюцинации, неверно выделенные предложения.

## Инструкции Для Генерации Датасетов Сторонней LLM

Этот раздел можно передавать внешней LLM как техническое задание на генерацию
данных. Для каждого набора LLM должна вернуть только валидный JSON без Markdown,
комментариев и пояснительного текста.

Общие правила генерации:

- язык данных: русский;
- не использовать реальные персональные данные, названия закрытых систем,
  телефоны, email или коммерческие сведения;
- `external_id` должны быть уникальными внутри одного набора;
- `PROJECT_ID_PLACEHOLDER` оставить как строку-заглушку, если реальный id
  проекта неизвестен;
- не добавлять поля, которых нет в указанной JSON-схеме;
- все эталонные ответы и `text_contains` должны дословно опираться на данные,
  которые есть в сгенерированном корпусе;
- для H1, H2, H4 и H5 в каждом кейсе в `metadata` указать `hypothesis`,
  `case_type` и, если применимо, `difficulty`: `easy`, `medium` или `hard`;
- для H3/RAG Eval не добавлять `metadata` в `cases`: импорт принимает это поле
  как служебное для совместимости, но не сохраняет и не использует в метриках;
- после генерации проверить JSON парсером и убедиться, что нет trailing comma.

### H1 Dataset Generation Prompt

Назначение: сгенерировать корпус для проверки ранней LLM-валидации требований.
Результат импортируется в `POST /admin/validation-eval/datasets/import`.

Скопируйте сторонней LLM такой промпт:

```text
Сгенерируй JSON для Validation Eval Dataset.
Верни только валидный JSON без Markdown.

Требования к набору:
- dataset_name: "H1 Validation Quality Benchmark"
- project_id: "PROJECT_ID_PLACEHOLDER"
- количество cases: 60
- 40 cases должны иметь expected_verdict="needs_rework"
- 20 cases должны иметь expected_verdict="approved"
- все тексты должны быть на русском языке
- предметная область: задачи управления документами, импорт реестров, статусы, уведомления, роли, отчеты, аудит, интеграции

Top-level JSON schema:
{
  "format": "json",
  "payload": {
    "dataset_name": "H1 Validation Quality Benchmark",
    "project_id": "PROJECT_ID_PLACEHOLDER",
    "cases": []
  }
}

Каждый case должен иметь поля:
{
  "external_id": "VAL-001",
  "title": "Название требования",
  "content": "Текст требования",
  "tags": ["tag1", "tag2"],
  "attachment_names": [],
  "custom_rules": [],
  "related_tasks": [],
  "historical_questions": [],
  "expected_verdict": "approved|needs_rework",
  "expected_issues": [],
  "expected_questions": [],
  "expected_context_questions": [],
  "metadata": {
    "hypothesis": "H1",
    "case_type": "...",
    "difficulty": "easy|medium|hard",
    "defect_types": []
  }
}

Для needs_rework cases добавь 1-3 expected_issues.
Каждый issue должен иметь:
{
  "code": "snake_case_code",
  "severity": "low|medium|high",
  "message": "Короткое описание дефекта",
  "source": "core"
}

Используй defect_types из списка:
- ambiguity
- incompleteness
- unverifiable
- contradiction
- missing_roles
- missing_permissions
- missing_error_handling
- missing_acceptance_criteria
- missing_nonfunctional_constraint
- missing_data_format
- weak_word
- integration_gap

Для approved cases:
- expected_issues должен быть []
- expected_questions должен быть []
- expected_context_questions должен быть []
- content должен содержать роль, действие, условия, результат и критерии проверки

Для needs_rework cases:
- content должен быть реалистичным, но содержать конкретные дефекты
- expected_questions должны быть связаны с expected_issues
- не делай все кейсы одинаковыми; используй разные типы задач и дефектов
```

Проверка результата H1 перед импортом:

- доля `needs_rework` находится в диапазоне 60-70%;
- у каждого `needs_rework` есть хотя бы один `expected_issue`;
- у каждого `approved` нет `expected_issues`;
- `source` у issues равен `core`;
- `expected_questions` не дублируют друг друга дословно в одном кейсе.

### H2 Dataset Generation Prompt

Назначение: сгенерировать корпус для проверки вклада проектных правил и
накопленного контекста. Результат импортируется в
`POST /admin/validation-eval/datasets/import` и запускается с variants
`core_only`, `core_custom`, `full`.

Скопируйте сторонней LLM такой промпт:

```text
Сгенерируй JSON для Validation Eval Dataset, который проверяет пользу проектных правил и исторического контекста.
Верни только валидный JSON без Markdown.

Требования к набору:
- dataset_name: "H2 Context Validation Benchmark"
- project_id: "PROJECT_ID_PLACEHOLDER"
- количество cases: 50
- каждый case должен содержать custom_rules и historical_questions
- минимум 35 cases должны иметь expected_verdict="needs_rework"
- минимум 30 cases должны содержать expected_context_questions
- все дефекты должны быть проектно-специфическими: их трудно уверенно вывести из базовых правил без знания локального правила или истории проекта

Top-level JSON schema:
{
  "format": "json",
  "payload": {
    "dataset_name": "H2 Context Validation Benchmark",
    "project_id": "PROJECT_ID_PLACEHOLDER",
    "cases": []
  }
}

Каждый case должен иметь поля:
{
  "external_id": "CTX-001",
  "title": "Название требования",
  "content": "Текст требования",
  "tags": ["tag1"],
  "attachment_names": [],
  "custom_rules": [
    {
      "title": "Название проектного правила",
      "description": "Описание локального правила проекта",
      "applies_to_tags": ["tag1"]
    }
  ],
  "related_tasks": [
    {
      "title": "Похожая историческая задача",
      "content": "Краткое описание решения или проблемы в прошлой задаче"
    }
  ],
  "historical_questions": [
    "Ранее заданный релевантный вопрос"
  ],
  "expected_verdict": "approved|needs_rework",
  "expected_issues": [],
  "expected_questions": [],
  "expected_context_questions": [],
  "metadata": {
    "hypothesis": "H2",
    "case_type": "custom_rule|historical_question|related_task|mixed_context",
    "difficulty": "easy|medium|hard"
  }
}

custom_rules должны описывать локальные правила проекта, например:
- для импорта должны быть указаны формат, лимит размера, частичные ошибки и журналирование
- для изменения статуса должны быть указаны права роли и аудит изменения
- для уведомлений должны быть указаны событие, получатели и канал
- для отчетов должны быть указаны фильтры, период, формат выгрузки и права доступа
- для интеграций должны быть указаны протокол, формат ошибки, повторная отправка и таймаут

Для needs_rework cases:
- добавь expected_issues с source="custom_rule" или source="context_questions"
- если дефект связан с проектным правилом, code должен начинаться с "custom_rule_"
- если ожидается вопрос из истории, добавь его в expected_context_questions
- historical_questions должны быть полезными и не должны быть случайными

Для approved cases:
- content должен явно соблюдать custom_rules
- expected_issues может быть []
- expected_context_questions может быть [] или содержать 1 полезный контрольный вопрос, если он не блокирует требование
```

Проверка результата H2 перед импортом:

- у каждого кейса есть хотя бы одно `custom_rules`;
- `applies_to_tags` пересекается с `tags`;
- `expected_context_questions` дословно связаны с `historical_questions`;
- у custom rule issues `source` равен `custom_rule`;
- набор содержит разные `case_type`, а не только импорт.

### H3 Dataset Generation Prompt

Назначение: сгенерировать корпус для RAG-вопросов по проектной памяти.
Результат импортируется в `POST /admin/rag-eval/datasets/import`.

Скопируйте сторонней LLM такой промпт:

```text
Сгенерируй JSON для RAG Eval Dataset.
Верни только валидный JSON без Markdown.

Требования к набору:
- dataset_name: "H3 RAG QA Benchmark"
- project_id: "PROJECT_ID_PLACEHOLDER"
- количество tasks: 20
- количество cases: 70
- 55 cases должны быть answerable: ответ есть в task content или attachments
- 15 cases должны быть unanswerable: в корпусе нет информации для ответа
- все expected_relevant для answerable cases должны ссылаться на реально существующие task_external_id
- text_contains должен быть дословной подстрокой из content задачи или content вложения
- attachments должны быть только текстовыми
- не добавляй metadata в cases

Top-level JSON schema:
{
  "format": "json",
  "payload": {
    "dataset_name": "H3 RAG QA Benchmark",
    "project_id": "PROJECT_ID_PLACEHOLDER",
    "tasks": [],
    "cases": []
  }
}

Каждый task должен иметь:
{
  "external_id": "TASK-001",
  "title": "Название задачи",
  "content": "Описание задачи с фактами, по которым можно задавать вопросы",
  "tags": ["tag1", "tag2"],
  "attachments": [
    {
      "filename": "source-001.txt",
      "content_type": "text/plain",
      "content": "Текстовый источник с дополнительными фактами"
    }
  ]
}

Каждый case должен иметь:
{
  "external_id": "RAG-001",
  "task_external_id": "TASK-001",
  "question": "Вопрос пользователя",
  "expected_answer": "Эталонный ответ",
  "expected_relevant": [
    {
      "task_external_id": "TASK-001",
      "source_type": "task_content|attachment_text",
      "text_contains": "Дословная подстрока из источника"
    }
  ]
}

Для answerable cases:
- expected_answer должен следовать только из task content или attachments
- expected_relevant должен содержать 1-2 источника
- question должен быть естественным, как вопрос разработчика, тестировщика, аналитика или менеджера

Для unanswerable cases:
- expected_relevant должен быть []
- expected_answer должен явно говорить, что в проектном контексте нет данных
- question должен быть правдоподобным, но ответ на него нельзя найти в tasks или attachments

Покрой типы вопросов:
- текущая задача
- связанная задача
- вложение
- правило обработки ошибок
- права доступа
- аудит
- формат импорта или выгрузки
- negative case без контекста
```

Проверка результата H3 перед импортом:

- все `task_external_id` в cases существуют в `tasks`;
- каждый `text_contains` является дословной подстрокой одного источника;
- у negative cases `expected_relevant` равен `[]`;
- вопросы не требуют внешних знаний за пределами корпуса;
- нет противоречий между `expected_answer` и источником.

### H4 Dataset Generation Prompt

Назначение: сгенерировать корпус сообщений для проверки выделения предложений
изменений. Результат отправляется в `POST /admin/change-proposal-eval/run`.

Скопируйте сторонней LLM такой промпт:

```text
Сгенерируй JSON для Change Proposal Eval.
Верни только валидный JSON без Markdown.

Требования к набору:
- project_id: "PROJECT_ID_PLACEHOLDER"
- config.mode: "route_then_extract"
- config.semantic_match_threshold: 0.55
- количество cases: 60
- 24 cases: явные предложения изменений
- 15 cases: неявные предложения изменений
- 12 cases: обычные вопросы или обсуждения без предложения изменения
- 9 cases: дубли или близкие по смыслу предложения

Top-level JSON schema:
{
  "project_id": "PROJECT_ID_PLACEHOLDER",
  "config": {
    "mode": "route_then_extract",
    "semantic_match_threshold": 0.55
  },
  "cases": []
}

Каждый case должен иметь:
{
  "external_id": "PROP-001",
  "task_id": null,
  "task_title": "Название задачи",
  "task_status": "draft|validating|needs_rework|awaiting_approval|ready_for_dev|in_progress|ready_for_testing|testing|done",
  "task_content": "Текущее описание задачи",
  "message_content": "Сообщение участника команды",
  "requested_agent": null,
  "expected_is_proposal": true,
  "expected_proposal_text": "Нормализованный текст предложения изменения",
  "expected_duplicate": false,
  "expected_duplicate_of": null,
  "expected_action": "create|skip_duplicate|ignore",
  "metadata": {
    "hypothesis": "H4",
    "case_type": "explicit_proposal|implicit_proposal|question_not_proposal|discussion_not_proposal|duplicate_proposal",
    "difficulty": "easy|medium|hard"
  }
}

Правила для explicit_proposal:
- message_content явно содержит "добавить", "изменить", "нужно сделать", "предлагаю"
- expected_is_proposal=true
- expected_action="create"
- expected_proposal_text должен быть кратким, без вводных слов и без автора сообщения

Правила для implicit_proposal:
- message_content звучит как проблема или замечание, но подразумевает изменение требования
- expected_is_proposal=true
- expected_action="create"
- expected_proposal_text должен формализовать подразумеваемое изменение

Правила для question_not_proposal:
- message_content является вопросом, который не меняет требование
- expected_is_proposal=false
- expected_proposal_text=null
- expected_action="ignore"

Правила для discussion_not_proposal:
- message_content является комментарием, подтверждением, сомнением или обсуждением без конкретного изменения
- expected_is_proposal=false
- expected_proposal_text=null
- expected_action="ignore"

Правила для duplicate_proposal:
- сначала в наборе должен быть исходный кейс с expected_action="create"
- duplicate case должен иметь expected_is_proposal=true
- expected_duplicate=true
- expected_duplicate_of должен ссылаться на external_id исходного кейса
- expected_action="skip_duplicate"
- expected_proposal_text должен совпадать по смыслу с исходным предложением

Не генерируй сообщения, где невозможно понять, есть ли предложение изменения.
Не смешивай в одном message_content два независимых предложения изменения.
```

Проверка результата H4 перед запуском:

- `expected_action="ignore"` только у `expected_is_proposal=false`;
- у всех proposal cases заполнен `expected_proposal_text`;
- каждый `expected_duplicate_of` ссылается на существующий более ранний кейс;
- duplicate cases не должны быть первыми в наборе;
- `expected_proposal_text` является нормализованным предложением, а не копией
  всего сообщения.

### H5 Dataset Generation Prompt

Назначение: сгенерировать корпус для проверки адаптации системы к проектному
контексту через повторное использование вопросов из истории задач. Результат
импортируется в `POST /admin/adaptation-eval/datasets/import`.

Скопируйте сторонней LLM такой промпт:

```text
Сгенерируй JSON для Adaptation Eval Dataset.
Верни только валидный JSON без Markdown.

Требования к набору:
- dataset_name: "H5 Adaptation Capability Benchmark"
- project_id: "PROJECT_ID_PLACEHOLDER"
- количество cases: 40
- все тексты должны быть на русском языке
- предметная область: задачи управления документами, импорт реестров, статусы, уведомления, роли, отчеты, аудит, интеграции
- 12 cases scenario_type="positive": прошлый опыт должен помочь новой задаче
- 8 cases scenario_type="partial_match": релевантна только часть исторического контекста
- 8 cases scenario_type="negative_control": похожая история есть, но применять ее нельзя
- 6 cases scenario_type="noise": релевантный вопрос скрыт среди нерелевантных сообщений
- 6 cases scenario_type="regression": корректная новая задача не должна ухудшаться из-за памяти

Top-level JSON schema:
{
  "dataset_name": "H5 Adaptation Capability Benchmark",
  "project_id": "PROJECT_ID_PLACEHOLDER",
  "cases": []
}

Каждый case должен иметь поля:
{
  "external_id": "ADAPT-001",
  "scenario_type": "positive|negative_control|partial_match|noise|regression",
  "historical_tasks": [
    {
      "title": "Историческая задача",
      "content": "Описание исторической задачи",
      "tags": ["tag1"],
      "chat_messages": [
        "Сообщение команды с уточняющим вопросом или ответом"
      ]
    }
  ],
  "probe_task": {
    "title": "Новая задача",
    "content": "Описание новой задачи",
    "tags": ["tag1"],
    "custom_rules": [],
    "related_tasks": [],
    "attachment_names": []
  },
  "expected_captured_questions": [],
  "expected_retrieved_questions": [],
  "expected_context_questions": [],
  "expected_verdict": "approved|needs_rework",
  "expected_context_issues": [],
  "metadata": {
    "hypothesis": "H5",
    "case_type": "reused_question|partial_reuse|negative_control|noise|regression",
    "difficulty": "easy|medium|hard"
  }
}

Правила для positive cases:
- historical_tasks должны содержать 1-3 вопроса, которые полезны для новой задачи
- expected_captured_questions должны включать эти вопросы
- expected_retrieved_questions должны включать вопросы, которые должны быть найдены по probe_task
- expected_context_questions должны содержать применимые к probe_task вопросы
- expected_verdict обычно "needs_rework", если вопрос выявляет пропуск
- expected_context_issues должны описывать пропуск с source="context_questions" и code="context_question"

Правила для partial_match cases:
- исторический контекст должен содержать несколько вопросов, но к probe_task применима только часть
- expected_retrieved_questions могут быть шире, чем expected_context_questions
- не добавляй в expected_context_questions вопросы, которые не относятся к новой задаче

Правила для negative_control cases:
- исторические задачи должны быть похожи по словам или тегам, но нерелевантны по смыслу
- expected_context_questions должен быть []
- expected_context_issues должен быть []
- expected_verdict должен быть "approved", если probe_task сама по себе полная

Правила для noise cases:
- добавь в chat_messages нерелевантные обсуждения и один релевантный вопрос
- expected_captured_questions должны содержать только полезные вопросы
- expected_retrieved_questions должны содержать релевантный вопрос, несмотря на шум

Правила для regression cases:
- probe_task должна уже содержать ответ на исторический вопрос
- expected_context_questions должен быть [] или содержать только неблокирующий контрольный вопрос
- expected_context_issues должен быть []
- expected_verdict должен быть "approved"

Не генерируй внешние факты, которые нельзя проверить по historical_tasks или probe_task.
Не используй одинаковые формулировки во всех кейсах.
```

Проверка результата H5 перед импортом:

- top-level JSON не содержит `format` и `payload`;
- `scenario_type` входит в список `positive`, `negative_control`,
  `partial_match`, `noise`, `regression`;
- у каждого case есть хотя бы одна `historical_tasks` и один `probe_task`;
- `expected_context_issues` используют `source="context_questions"`;
- в `negative_control` и `regression` нет блокирующих контекстных замечаний;
- ожидаемые вопросы не противоречат тексту исторических задач и новой задачи.

## H1. Ранняя Проверка Требований

**Гипотеза:** LLM-агент валидации способен выявлять дефектные требования на
размеченном корпусе с полнотой не ниже 85% при качестве найденных замечаний по
F1 не ниже 70%.

**Данные:** `Validation Eval Dataset`, 40-100 требований, 60-70% дефектных и
30-40% корректных. Для каждого кейса нужны `title`, `content`, `tags`,
`expected_verdict`, `expected_issues`, `expected_questions`, `metadata`.

**Инструмент:** `Validation Eval`, вариант `full`. Дополнительно можно
использовать `QURE Eval` для проверки слабых слов и бинарного verdict.

**Метрики и пороги:**

| Метрика | Порог |
| --- | ---: |
| `verdict_recall` для дефектных требований | `>= 0.85` |
| `issue_f1` | `>= 0.70` |
| `issue_precision` | желательно `>= 0.70` |

## H2. Компенсация Разного Проектного Опыта

**Гипотеза:** использование проектных правил и накопленного контекста повышает
качество проверки требований по сравнению с базовой проверкой без проектной
памяти не менее чем на 10 п.п. по F1.

**Данные:** `Validation Eval Dataset`, 30-70 проектно-специфических кейсов.
Кейсы должны включать `custom_rules`, `historical_questions`, `related_tasks`,
ожидаемые `custom_rule` issues и `expected_context_questions`.

**Инструмент:** `Validation Eval` с тремя variants:

- `core_only`: базовые правила;
- `core_custom`: базовые + проектные правила;
- `full`: базовые + проектные правила + контекстные вопросы.

**Метрики и пороги:**

| Метрика | Порог |
| --- | ---: |
| `issue_f1(full) - issue_f1(core_only)` | `>= 0.10` |
| или `overall_question_f1(full) - overall_question_f1(core_only)` | `>= 0.10` |
| падение `issue_precision(full)` относительно `core_only` | `<= 0.05` |

## H3. Ответы По Проектной Памяти

**Гипотеза:** RAG-агент способен отвечать на типовые вопросы по проектному
контексту с корректностью не ниже 80% и подтверждением ответа релевантными
источниками не ниже 80%.

**Данные:** `RAG Eval Dataset`, 40-100 вопросов. Корпус должен содержать
синтетические задачи, текстовые вложения, проектные правила, исторические
решения и 15-20% negative cases, где правильный ответ: данных недостаточно.

**Инструмент:** `RAG Eval`.

Рекомендуемая конфигурация:

- `indexing_mode = all`;
- `retrieval_limit = 5`;
- `run_answer_agent = true`;
- `run_llm_judge = true`;
- `run_bm25_baseline = true`;
- `include_cross_task = true`;
- `use_query_rewriter = true`;
- `use_hybrid_rerank = true`.

**Метрики и пороги:**

| Метрика | Порог |
| --- | ---: |
| доля `correctness = correct` | `>= 0.80` |
| доля `groundedness = grounded` | `>= 0.80` |
| `recall_at_3` | `>= 0.80` |
| `mrr` | `>= 0.70` |
| корректные отказы на negative cases | `>= 0.80` |
| `rag_vs_bm25_mrr_delta` | желательно `>= 0.10` |

## H4. Формализация Неформальных Договоренностей

**Гипотеза:** агент обработки коммуникации способен выделять предложения
изменений из сообщений команды и сохранять их как структурированные артефакты с
F1 не ниже 75%.

**Данные:** `Change Proposal Eval Dataset`, 40-80 сообщений. Баланс набора:
40% явные предложения, 25% неявные предложения, 20% обычные вопросы или
обсуждения, 15% дубли или близкие по смыслу предложения.

**Инструмент:** `POST /admin/change-proposal-eval/run`.

Endpoint выполняет одноразовый прогон без создания eval-таблиц:

- в режиме `route_then_extract` сначала проверяет маршрутизацию сообщения;
- если маршрут ведет в `change-tracker`, запускает извлечение предложения;
- сравнивает `proposal_text`, действие `create/skip_duplicate/ignore` и флаг
  дубликата с эталонной разметкой;
- возвращает case results и summary metrics.

**Метрики и пороги:**

| Метрика | Порог |
| --- | ---: |
| `proposal_f1` | `>= 0.75` |
| `proposal_text_f1` | `>= 0.75` |
| `false_creation_rate` | желательно `<= 0.15` |
| `duplicate_f1` при проверке дублей | желательно `>= 0.70` |

## H5. Адаптация К Проектному Опыту

**Гипотеза:** система способна адаптировать проверку новых требований к
накопленному проектному опыту: извлекать уточняющие вопросы из истории задач,
находить релевантные вопросы для новой задачи и использовать их как
контекстные замечания при валидации.

**Данные:** `Adaptation Eval Dataset`, 30-50 кейсов. Каждый кейс должен
содержать исторические задачи с сообщениями команды, новую `probe_task`,
ожидаемые извлеченные вопросы, ожидаемые найденные вопросы, ожидаемые
контекстные вопросы и ожидаемые контекстные замечания.

**Инструмент:** `Adaptation Eval`.

Рекомендуемая конфигурация:

- `retrieval_limit = 5`;
- `cleanup_synthetic_tasks = true`;
- `run_match_judge = true`;
- `judge_match_confidence_min = 0.75`;
- `quality_gates.capture_recall_min = 0.90`;
- `quality_gates.retrieval_recall_at_k_min = 0.80`;
- `quality_gates.context_question_f1_min = 0.75`;
- `quality_gates.context_issue_f1_min = 0.70`;
- `quality_gates.duplicate_rate_max = 0.10`.

**Метрики и пороги:**

| Метрика | Порог |
| --- | ---: |
| `capture_recall` | `>= 0.90` |
| `retrieval_recall_at_k` | `>= 0.80` |
| `retrieval_mrr` | `>= 0.70` |
| `context_question_f1` | `>= 0.75` |
| `context_issue_f1` | `>= 0.70` |
| `overall_question_duplicate_rate` | `<= 0.10` |
| `gate_status` | `passed` |

Важно: в текущей реализации `Adaptation Eval` проверяет адаптацию через
повторное использование вопросов и контекстных замечаний. Он не проверяет
дообучение LLM и не покрывает выделение предложений изменений; для предложений
изменений используется H4.

## Сводная Таблица Результатов

В ВКР результаты удобно фиксировать так:

| Гипотеза | Метрика | Порог | Результат | Вывод |
| --- | ---: | ---: | ---: | --- |
| H1 | `verdict_recall` | `>= 0.85` | ... | ... |
| H1 | `issue_f1` | `>= 0.70` | ... | ... |
| H2 | `issue_f1_delta` | `>= 0.10` | ... | ... |
| H3 | `correctness` | `>= 0.80` | ... | ... |
| H3 | `groundedness` | `>= 0.80` | ... | ... |
| H4 | `proposal_f1` | `>= 0.75` | ... | ... |
| H5 | `capture_recall` | `>= 0.90` | ... | ... |
| H5 | `retrieval_recall_at_k` | `>= 0.80` | ... | ... |
| H5 | `context_question_f1` | `>= 0.75` | ... | ... |

Корректная формулировка вывода: "по результатам эксперимента на размеченном
синтетическом корпусе гипотеза подтверждена / частично подтверждена / не
подтверждена при заданных порогах".
