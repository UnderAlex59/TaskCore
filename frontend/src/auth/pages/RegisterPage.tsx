import axios from "axios";
import { startTransition, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { authApi } from "@/api/authApi";
import { useAuthStore } from "@/store/authStore";

export default function RegisterPage() {
  const navigate = useNavigate();
  const setAccessToken = useAuthStore((state) => state.setAccessToken);
  const setUser = useAuthStore((state) => state.setUser);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  function getErrorMessage(err: unknown) {
    if (axios.isAxiosError(err)) {
      const detail = err.response?.data?.detail;
      if (typeof detail === "string" && detail.trim().length > 0) {
        return detail;
      }

      if (Array.isArray(detail) && detail.length > 0) {
        const firstMessage = detail.find(
          (item): item is { msg?: string } =>
            typeof item === "object" && item !== null,
        )?.msg;
        if (
          typeof firstMessage === "string" &&
          firstMessage.trim().length > 0
        ) {
          return firstMessage;
        }
      }
    }

    return "Не удалось зарегистрироваться. Укажите уникальный email, минимум одну заглавную букву и одну цифру.";
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await authApi.register(email, password, fullName);
      const { data: tokenData } = await authApi.login(email, password);
      setAccessToken(tokenData.access_token);
      const { data: userData } = await authApi.me();
      setUser(userData);
      startTransition(() => {
        navigate("/projects", { replace: true });
      });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex min-h-[100svh] items-center justify-center px-3 py-4 sm:px-4 sm:py-8">
      <div className="glass-panel grid w-full max-w-4xl gap-6 border border-black/10 p-6 shadow-panel sm:p-8 lg:grid-cols-[0.95fr_1.05fr] lg:p-10">
        <section>
          <Link
            className="section-eyebrow inline-flex items-center gap-2"
            to="/"
          >
            <span aria-hidden="true">/</span>
            На главную
          </Link>
          <p className="mt-8 section-eyebrow">Регистрация</p>
          <h1 className="mt-3 text-balance text-3xl font-bold text-ink sm:text-4xl">
            Создайте аккаунт в системе.
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate/80">
            После регистрации вы получите доступ к проектам, обсуждениям задач и
            проверке требований в одном интерфейсе. Первый аккаунт автоматически
            становится администратором платформы.
          </p>
          <div className="mt-8 space-y-3 text-sm leading-7 text-slate/75">
            <p>1. Создайте аккаунт с надёжным паролем.</p>
            <p>2. Откройте рабочее пространство и создайте первый проект.</p>
            <p>
              3. Уточняйте задачи через чат, проверку и согласование изменений.
            </p>
          </div>
        </section>

        <section>
          <p className="mt-1 max-w-2xl text-sm leading-7 text-slate/80">
            Первый зарегистрированный аккаунт автоматически становится
            администратором платформы. Все следующие аккаунты создаются как
            разработчики и могут быть повышены из админ-консоли.
          </p>

          <form
            className="mt-8 grid gap-5 sm:grid-cols-2"
            onSubmit={handleSubmit}
          >
            <label className="block sm:col-span-2">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Полное имя
              </span>
              <input
                autoComplete="name"
                className="ui-field text-base"
                name="full-name"
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Алексей Аналитик"
                required
                type="text"
                value={fullName}
              />
            </label>

            <label className="block sm:col-span-2">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Электронная почта
              </span>
              <input
                autoComplete="email"
                className="ui-field text-base"
                name="email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="analyst@example.ru"
                required
                spellCheck={false}
                type="email"
                value={email}
              />
            </label>

            <label className="block sm:col-span-2">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Пароль
              </span>
              <input
                autoComplete="new-password"
                className="ui-field text-base"
                minLength={8}
                name="password"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Не менее 8 символов, заглавная буква и цифра"
                required
                type="password"
                value={password}
              />
            </label>

            {error ? (
              <p
                aria-live="polite"
                className="rounded-[10px] bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 sm:col-span-2"
              >
                {error}
              </p>
            ) : null}

            <button
              className="ui-button-primary px-5 py-3 font-bold uppercase tracking-[0.12em] sm:col-span-2"
              disabled={isLoading}
              type="submit"
            >
              {isLoading ? "Создаём аккаунт..." : "Создать аккаунт"}
            </button>
          </form>

          <p className="mt-6 text-sm text-slate/75">
            Уже зарегистрированы?{" "}
            <Link className="font-bold text-ember" to="/login">
              Войти
            </Link>
          </p>
        </section>
      </div>
    </div>
  );
}
