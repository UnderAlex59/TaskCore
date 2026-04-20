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

    return "Не удалось зарегистрироваться. Укажите уникальный email и корректный пароль.";
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
    <div className="min-h-[100svh] bg-[#f5f6f8] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto grid max-w-[1180px] gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-8">
          <Link
            className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84] hover:text-[#0c66e4]"
            to="/"
          >
            На главную
          </Link>
          <p className="mt-8 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
            Регистрация
          </p>
          <h1 className="mt-4 text-3xl font-semibold leading-tight text-[#172b4d]">
            Создайте рабочий аккаунт.
          </h1>
          <p className="mt-4 text-sm leading-7 text-[#44546f]">
            После регистрации вы получите доступ к проектам, требованиям и
            командной работе по задачам. Первый аккаунт в системе становится
            администратором платформы.
          </p>
          <div className="mt-8 space-y-3 text-sm leading-6 text-[#44546f]">
            <p>1. Создайте аккаунт с рабочими данными.</p>
            <p>2. Откройте проекты и настройте состав команды.</p>
            <p>3. Ведите постановки и изменения в одном рабочем контексте.</p>
          </div>
        </section>

        <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-8 lg:px-8">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
            Новый пользователь
          </p>
          <h2 className="mt-3 text-2xl font-semibold text-[#172b4d]">
            Зарегистрировать аккаунт
          </h2>
          <p className="mt-3 text-sm leading-7 text-[#44546f]">
            Используйте имя, email и пароль. После успешной регистрации вход
            выполнится автоматически.
          </p>

          <form
            className="mt-8 grid gap-5 sm:grid-cols-2"
            onSubmit={handleSubmit}
          >
            <label className="block sm:col-span-2">
              <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
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
              <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
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
              <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
                Пароль
              </span>
              <input
                autoComplete="new-password"
                className="ui-field text-base"
                minLength={8}
                name="password"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Не менее 8 символов"
                required
                type="password"
                value={password}
              />
            </label>

            {error ? (
              <p
                aria-live="polite"
                className="rounded-[12px] border border-[rgba(174,46,36,0.18)] bg-[#fdecec] px-4 py-3 text-sm text-[#ae2e24] sm:col-span-2"
              >
                {error}
              </p>
            ) : null}

            <button
              className="ui-button-primary justify-center sm:col-span-2"
              disabled={isLoading}
              type="submit"
            >
              {isLoading ? "Создаем аккаунт..." : "Создать аккаунт"}
            </button>
          </form>

          <p className="mt-6 text-sm text-[#44546f]">
            Уже зарегистрированы?{" "}
            <Link className="font-semibold text-[#0c66e4]" to="/login">
              Войти
            </Link>
          </p>
        </section>
      </div>
    </div>
  );
}
