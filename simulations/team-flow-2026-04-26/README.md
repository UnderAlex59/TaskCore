# Team Flow Simulation 2026-04-26

        ## Контур

        - API: `http://127.0.0.1:8080/api`
        - Проект: `Командная эмуляция магистерской 2026-04-26`
        - Project ID: `2c64dafa-77bd-4e34-9137-8855897d51c9`

        ## Учётки

        - admin: `admin@example.com` / `Password1` / роль `ADMIN`
- analyst: `analyst@example.com` / `Password1` / роль `ANALYST`
- developer: `developer@example.com` / `Password1` / роль `DEVELOPER`
- tester: `tester@example.com` / `Password1` / роль `TESTER`

        ## Теги

        - workflow, roles, forms, attachments, validation, notifications, import, reports, integration, audit, dashboard, security

        ## LLM-проверка

        - Автоматически созданный профиль по умолчанию (openai/gpt-4o): ok=not-tested required=False default=True
- Автоматически созданный профиль для агента qa (openai/gpt-4o-mini): ok=not-tested required=False default=False
- Автоматически созданный профиль для агента change-tracker (openrouter/minimax/minimax-m2.5:free): ok=True required=True default=False

        ## Задачи

        | № | Заголовок | Теги | Финальный статус | Сообщений | Backlog сохранён | Backlog reused |
        | --- | --- | --- | --- | ---: | --- | --- |
        | 1 | Жизненный цикл заявки на закупку | workflow, validation, roles | ready_for_dev | 7 | Что делать, если руководитель уже согласовал заявку, а после смены подразделения инициатора финансовый контролёр возвращает её на доработку? | нет |
| 2 | Роли участников и ограничения переходов статусов | workflow, roles, validation | ready_for_dev | 6 | Если временный заместитель подписал заявку в последний день делегирования, а основной руководитель вернулся через час, кто может отменить это решение? | нет |
| 3 | Динамическая форма заявки и обязательные поля | forms, workflow, validation | ready_for_dev | 4 | нет | нет |
| 4 | Вложения к заявке и правила допустимых файлов | attachments, validation, workflow | ready_for_dev | 5 | Что делать со сканированным PDF без OCR, если по регламенту из него нельзя автоматически извлечь текст для последующей проверки? | нет |
| 5 | Уведомления о смене статуса и эскалациях | notifications, validation, workflow | ready_for_dev | 4 | нет | нет |
| 6 | Импорт заявителей из CSV | import, attachments, validation | ready_for_dev | 6 | Что делать, если в CSV есть две строки без external_id, но с одинаковыми ФИО и разными подразделениями? | нет |
| None | Экспорт и архив согласованных заявок | security, integration, reports | needs_rework | 4 | нет | нет |
| None | Дашборд SLA по просроченным заявкам | dashboard, reports, audit | needs_rework | 4 | нет | нет |
| None | Аудит массовых изменений маршрута согласования | audit, integration, reports | needs_rework | 4 | нет | нет |
| None | Синхронизация статусов с внешней CRM | integration, reports, audit | needs_rework | 4 | нет | нет |

        ## Артефакты

        - `tasks/` содержит исходные описания задач.
        - `history/` содержит поминутную историю по каждой задаче.
        - `attachments/` содержит текстовые файлы, загруженные через API.
        - `summary.json` содержит машинно-читаемый итог прогона.
