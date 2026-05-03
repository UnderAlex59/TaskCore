# Frontend

Frontend - React/Vite SPA для Task Platform MVP. Интерфейс ориентирован на рабочий production-сценарий: проекты, задачи, валидация требований, чат, предложения изменений, профиль и админские разделы. Визуальный стиль должен оставаться сдержанным, деловым и прикладным, без промо-лендингового или "AI startup" вида в рабочих экранах.

## Стек

- React 19
- TypeScript
- Vite
- React Router
- Zustand
- Axios
- Tailwind CSS
- Vitest, Testing Library, jsdom
- ESLint, Prettier

## Структура

```text
frontend/
|-- src/
|   |-- api/          # typed API clients и axios instance
|   |-- auth/         # AuthProvider, guards, login/register pages
|   |-- features/     # доменные экраны
|   |-- shared/       # общие компоненты, hooks, lib
|   |-- store/        # Zustand stores
|   |-- test/         # setup тестовой среды
|   |-- App.tsx       # routing
|   `-- main.tsx
|-- package.json
|-- vite.config.ts
|-- tailwind.config.ts
`-- README.md
```

## Маршруты

Публичные:

- `/` - стартовая страница.
- `/login` - вход.
- `/register` - регистрация.

Приватные:

- `/profile` - профиль текущего пользователя.
- `/projects` - список проектов.
- `/projects/:projectId/tasks` - задачи проекта.
- `/projects/:projectId/tasks/new` - создание задачи.
- `/projects/:projectId/tasks/:taskId` - рабочая страница задачи.
- `/projects/:projectId/tasks/:taskId/chat` - чат задачи.

Админские маршруты доступны через `RoleGuard` для `ADMIN`:

- `/admin/monitoring` - мониторинг, активность, LLM-метрики и audit.
- `/admin/qdrant` - состояние Qdrant, coverage и scenario probes.
- `/admin/llm-requests` - журнал LLM-вызовов.
- `/admin/validation-questions` - банк вопросов валидации.
- `/admin/task-tags` - справочник тегов.
- `/admin/providers` - LLM-провайдеры, default provider, runtime settings и agent overrides.
- `/admin/vision-test` - проверка Vision-сценария.
- `/admin/agent-prompts` - prompt configs и restore версий.
- `/admin/users` - пользователи.
- `/admin/projects/:projectId/rules` - кастомные правила проекта.

## API-клиенты

- `api/client.ts` - Axios instance, access token, refresh queue, редирект на login при потере сессии.
- `api/authApi.ts` - register, login, refresh, logout, me, sessions.
- `api/projectsApi.ts` - проекты, участники, правила.
- `api/tasksApi.ts` - задачи, workflow-переходы, validate, commit, approve, upload, tag suggestions.
- `api/chatApi.ts` - HTTP-сообщения и WebSocket.
- `api/proposalsApi.ts` - предложения изменений.
- `api/adminApi.ts` - monitoring, LLM runtime, prompts, Qdrant, audit, validation questions, tags, vision test.
- `api/taskTagsApi.ts` - проектные теги.
- `api/usersApi.ts` - пользователи и профиль.

## Авторизация

Frontend хранит access token в Zustand store в памяти приложения. Refresh token хранится на backend в `httpOnly` cookie. `AuthProvider` при старте пытается восстановить сессию, `ProtectedRoute` закрывает приватные страницы, `RoleGuard` ограничивает админские разделы.

Поведение API-клиента:

- добавляет Bearer access token к запросам;
- при 401 выполняет refresh;
- объединяет параллельные refresh-запросы в очередь;
- при невозможности восстановить сессию очищает состояние и отправляет пользователя на login.

## Функциональные модули

- `features/landing` - стартовый экран продукта.
- `features/projects` - список проектов, карточки, создание проекта.
- `features/tasks` - список задач, форма, рабочее пространство, документ задачи, вложения, валидация, workflow-действия.
- `features/chat` - окно чата, список сообщений, ввод, bubble-компоненты и agent messages.
- `features/profile` - профиль, имя, никнейм, аватар.
- `features/admin` - layout админки, monitoring, Qdrant, providers, prompts, users, tags, validation questions, rules, vision test.
- `shared/components` - layout, avatar, confirm dialog, spinner, tag multi select, trend chart.
- `shared/lib` - обработка API-ошибок, локализация, user profile helpers.
- `store` - auth и UI state.

## Взаимодействие с backend

`VITE_API_URL` задает base URL. В production используется `/api`, потому что frontend обслуживается через nginx и proxy. В dev Vite проксирует `/api` на `VITE_API_PROXY_TARGET`.

`vite.config.ts`:

- включает alias `@` на `src`;
- проксирует HTTP и WebSocket;
- удаляет префикс `/api` при отправке запроса на backend.

Минимальный `.env`:

```env
VITE_API_URL=/api
VITE_API_PROXY_TARGET=http://localhost:8000
```

Если frontend должен ходить напрямую в backend без Vite proxy:

```env
VITE_API_URL=http://localhost:8000
```

## Рабочие сценарии UI

- Аналитик создает задачу, добавляет описание, теги и вложения.
- Пользователь запускает валидацию, получает issues/questions/verdict из LangGraph.
- После успешной проверки задача переходит на подтверждение и назначение команды.
- Разработчик и тестировщик ведут задачу по workflow-статусам.
- Участники обсуждают задачу в чате.
- `@qa` и другие agent aliases направляют сообщение в нужный LangGraph subgraph.
- ChangeTracker формирует предложения изменений, которые можно принять или отклонить.
- Администратор управляет LLM-провайдерами, overrides, prompts, Qdrant, audit и справочниками.

## UX-ориентиры

- Рабочие экраны должны быть плотными, читаемыми и предсказуемыми.
- Карточки использовать для повторяющихся сущностей, а не как универсальный декоративный контейнер.
- Статусы, действия и ошибки должны быть видны без лишнего текста.
- Русские UI-строки хранить в нормальном UTF-8.
- Не добавлять визуальные элементы, которые выглядят как типовой AI-лендинг, если они не помогают рабочему сценарию.

## Запуск

```bash
cd frontend
npm install
npm run dev
```

## Проверки

```bash
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

Из корня:

```bash
make frontend-lint
make frontend-test
make frontend-build
```
