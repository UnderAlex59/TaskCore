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
    <div className="flex min-h-[100svh] items-center px-3 py-4 sm:px-4 sm:py-8">
      <div className="mx-auto grid w-full max-w-6xl gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="glass-panel mesh-card flex flex-col justify-between border border-black/10 p-6 shadow-panel sm:p-8 lg:p-10">
          <div>
            <Link
              className="section-eyebrow inline-flex items-center gap-2"
              to="/"
            >
              <span aria-hidden="true">/</span>
              На главную
            </Link>
            <p className="mt-8 section-eyebrow">Вход в систему</p>
            <h1 className="mt-4 max-w-2xl text-balance text-4xl font-bold leading-tight text-ink sm:text-5xl">
              Войдите, чтобы работать с требованиями, согласованиями и задачами в
              едином контексте.
            </h1>
            <p className="mt-6 max-w-xl text-base leading-8 text-slate/85">
              Используйте рабочее пространство, чтобы проверять задачи,
              рассматривать изменения и вести обсуждение прямо внутри требования.
            </p>
          </div>

          <div className="mt-10 grid gap-4 sm:grid-cols-3">
            {[
              { label: "Чат задачи", value: "Всегда рядом" },
              { label: "Проверка", value: "В одном потоке" },
              { label: "Админка", value: "С учётом ролей" },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-[10px] border border-black/10 bg-white/70 p-4"
              >
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate/65">
                  {item.label}
                </p>
                <p className="mt-2 text-lg font-bold text-ink">{item.value}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="glass-panel border border-black/10 p-6 shadow-panel sm:p-8 lg:p-10">
          <p className="section-eyebrow">Авторизация</p>
          <h2 className="mt-3 text-balance text-2xl font-bold text-ink sm:text-3xl">
            Продолжить работу.
          </h2>
          <p className="mt-3 text-sm leading-7 text-slate/75">
            Введите данные, чтобы открыть проекты, задачи и рабочее пространство
            с чатом по требованиям.
          </p>

          <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
            <label className="block">
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

            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
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
                className="rounded-[10px] bg-red-50 px-4 py-3 text-sm font-semibold text-red-700"
              >
                {error}
              </p>
            ) : null}

            <button
              className="ui-button-primary w-full px-5 py-3 font-bold uppercase tracking-[0.12em]"
              disabled={isLoading}
              type="submit"
            >
              {isLoading ? "Входим..." : "Войти"}
            </button>
          </form>

          <p className="mt-6 text-sm text-slate/75">
            Ещё нет аккаунта?{" "}
            <Link className="font-bold text-ember" to="/register">
              Зарегистрироваться
            </Link>
          </p>
        </section>
      </div>
    </div>
  );
}
