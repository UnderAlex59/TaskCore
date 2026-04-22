# Frontend

Frontend - React/Vite SPA для Task Platform MVP. Интерфейс рассчитан на рабочий production-сценарий: проекты, задачи, валидация требований, чат, предложения изменений, профиль и админские разделы без маркетинговой стилистики.

## Стек

- React 19
- TypeScript
- Vite
- React Router
- Zustand
- Axios
- Tailwind CSS
- Vitest, Testing Library
- ESLint, Prettier

## Структура

```text
frontend/
├── src/
│   ├── api/          # typed API clients
│   ├── auth/         # AuthProvider, guards, login/register pages
│   ├── features/     # доменные экраны
│   ├── shared/       # общие компоненты, hooks, lib
│   ├── store/        # Zustand stores
│   ├── test/         # setup тестов
│   ├── App.tsx       # routing
│   └── main.tsx
├── package.json
├── vite.config.ts
└── README.md
```

## Основные маршруты

- `/` - публичная стартовая страница.
- `/login`, `/register` - авторизация.
- `/profile` - профиль пользователя.
- `/projects` - список проектов.
- `/projects/:projectId/tasks` - задачи проекта.
- `/projects/:projectId/tasks/new` - создание задачи.
- `/projects/:projectId/tasks/:taskId` - рабочая страница задачи.
- `/projects/:projectId/tasks/:taskId/chat` - чат задачи.
- `/admin/monitoring` - мониторинг и audit.
- `/admin/validation-questions` - банк вопросов валидации.
- `/admin/task-tags` - справочник тегов.
- `/admin/providers` - LLM-провайдеры и agent overrides.
- `/admin/users` - пользователи.
- `/admin/projects/:projectId/rules` - кастомные правила проекта.

## API-клиенты

- `api/client.ts` - Axios instance, Bearer access token, refresh queue, редирект на login при потере сессии.
- `api/authApi.ts` - auth endpoints.
- `api/projectsApi.ts` - проекты и участники.
- `api/tasksApi.ts` - задачи, validate, approve, commit, upload.
- `api/chatApi.ts` - сообщения и WebSocket.
- `api/proposalsApi.ts` - предложения изменений.
- `api/adminApi.ts` - мониторинг и LLM runtime.
- `api/taskTagsApi.ts` - справочник тегов.
- `api/usersApi.ts` - пользователи.

## Функциональные модули

- `features/tasks` - список задач, форма, рабочая страница, панель валидации, вложения.
- `features/chat` - окно чата, список сообщений, ввод, bubble-сообщения.
- `features/admin` - layout админки, мониторинг, провайдеры, пользователи, теги, вопросы валидации, правила.
- `features/projects` - список проектов, карточки, создание.
- `features/profile` - профиль пользователя.
- `features/landing` - стартовый экран.

## Авторизация

Access token хранится в Zustand store в памяти приложения. Refresh token передается backend через `httpOnly` cookie. `AuthProvider` восстанавливает сессию при старте приложения, `ProtectedRoute` закрывает приватные маршруты, `RoleGuard` ограничивает админские разделы.

## Переменные окружения

```env
VITE_API_URL=/api
VITE_API_PROXY_TARGET=http://localhost:8000
```

В production `VITE_API_URL=/api`, потому что frontend обслуживается через reverse proxy. Для локальной разработки Vite проксирует API на backend.

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

Или из корня:

```bash
make frontend-lint
make frontend-test
make frontend-build
```

## UX-ориентиры

- Интерфейс должен оставаться сдержанным и прикладным.
- Рабочие экраны не должны выглядеть как промо-лендинг.
- Для задач важнее плотность информации, понятные статусы, быстрый доступ к валидации, команде, чату и истории предложений.
- Русские тексты в UI должны храниться в нормальной UTF-8 кодировке.
