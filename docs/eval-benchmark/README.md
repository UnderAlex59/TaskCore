# Eval Benchmark Templates

Каталог содержит стартовые JSON-шаблоны для экспериментальной проверки H1-H5.
Перед импортом замените `PROJECT_ID_PLACEHOLDER` на id проекта из локального
стенда и расширьте наборы до нужного объема:

- H1: 40-100 требований;
- H2: 30-70 проектно-специфических требований;
- H3: 40-100 вопросов к проектной памяти;
- H4: 40-80 сообщений команды.
- H5: 30-50 сценариев адаптации к проектному опыту.

Файлы:

- `h1_validation_quality.sample.json` - импорт в `POST /admin/validation-eval/datasets/import`;
- `h2_context_validation.sample.json` - импорт в `POST /admin/validation-eval/datasets/import`;
- `h3_rag_qa.sample.json` - импорт в `POST /admin/rag-eval/datasets/import`;
- `h4_change_proposal_eval.sample.json` - запуск через `POST /admin/change-proposal-eval/run`.
- `h5_adaptation_eval.sample.json` - импорт в `POST /admin/adaptation-eval/datasets/import`.

Подробные промпты и правила, по которым сторонняя LLM может сгенерировать
валидные расширенные наборы данных, описаны в
`docs/experimental-evaluation-plan.md` в разделе
"Инструкции Для Генерации Датасетов Сторонней LLM".
