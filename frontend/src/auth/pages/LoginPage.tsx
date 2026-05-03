import { startTransition, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { authApi } from "@/api/authApi";
import { useAuthStore } from "@/store/authStore";

export default function LoginPage() {
  const navigate = useNavigate();
  const setAccessToken = useAuthStore((state) => state.setAccessToken);
  const setUser = useAuthStore((state) => state.setUser);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const { data: tokenData } = await authApi.login(email, password);
      setAccessToken(tokenData.access_token);

      const { data: userData } = await authApi.me();
      setUser(userData);

      startTransition(() => {
        navigate("/projects", { replace: true });
      });
    } catch {
      setError("Неверный email или пароль.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-[100svh] bg-[#f5f6f8] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto grid max-w-[1180px] gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
        <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-8 lg:px-8 lg:py-10">
          <Link
            className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84] hover:text-[#0c66e4]"
            to="/"
          >
            На главную
          </Link>
          <p className="mt-8 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
            Вход
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight text-[#172b4d] sm:text-5xl">
            Откройте рабочее пространство команды.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-8 text-[#44546f]">
            После входа вы получите доступ к проектам, постановкам задач,
            проверке требований и общему обсуждению по каждой задаче.
          </p>

          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {[
              {
                title: "Проекты",
                value: "Рабочая область для команд и процессов",
              },
              {
                title: "Задачи",
                value: "Постановка оформляется как структурированный документ",
              },
              {
                title: "Проверка",
                value: "Проверка и изменения остаются рядом с задачей",
              },
            ].map((item) => (
              <article
                key={item.title}
                className="rounded-[16px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-4 py-4"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                  {item.title}
                </p>
                <p className="mt-2 text-sm leading-6 text-[#172b4d]">
                  {item.value}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-8 lg:px-8 lg:py-10">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
            Авторизация
          </p>
          <h2 className="mt-3 text-2xl font-semibold text-[#172b4d]">
            Продолжить работу
          </h2>
          <p className="mt-3 text-sm leading-7 text-[#44546f]">
            Используйте корпоративную почту и пароль для входа в систему.
          </p>

          <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
            <label className="block">
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

            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
                Пароль
              </span>
              <input
                autoComplete="current-password"
                className="ui-field text-base"
                name="password"
                minLength={8}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Ваш пароль"
                required
                type="password"
                value={password}
              />
            </label>

            {error ? (
              <p
                aria-live="polite"
                className="rounded-[12px] border border-[rgba(174,46,36,0.18)] bg-[#fdecec] px-4 py-3 text-sm text-[#ae2e24]"
              >
                {error}
              </p>
            ) : null}

            <button
              className="ui-button-primary w-full justify-center"
              disabled={isLoading}
              type="submit"
            >
              {isLoading ? "Входим..." : "Войти"}
            </button>
          </form>

          <p className="mt-6 text-sm text-[#44546f]">
            Еще нет аккаунта?{" "}
            <Link className="font-semibold text-[#0c66e4]" to="/register">
              Зарегистрироваться
            </Link>
          </p>
        </section>
      </div>
    </div>
  );
}
