import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { UserRole } from "@/api/authApi";
import { usersApi, type UserSummary } from "@/api/usersApi";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { getRoleLabel } from "@/shared/lib/locale";
import { useAuthStore } from "@/store/authStore";

const ROLE_OPTIONS: UserRole[] = ["ADMIN", "ANALYST", "DEVELOPER", "TESTER", "MANAGER"];

export default function UserList() {
  const navigate = useNavigate();
  const currentUser = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingUserId, setSavingUserId] = useState<string | null>(null);
  const [userPendingDeletion, setUserPendingDeletion] =
    useState<UserSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadUsers() {
    try {
      setLoading(true);
      setError(null);
      setUsers(await usersApi.list());
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить пользователей."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadUsers();
  }, []);

  async function handleRoleChange(userId: string, role: UserRole) {
    try {
      setSavingUserId(userId);
      const updated = await usersApi.update(userId, { role });
      setUsers((current) => current.map((user) => (user.id === userId ? updated : user)));
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось обновить роль пользователя."));
    } finally {
      setSavingUserId(null);
    }
  }

  async function handleActiveToggle(userId: string, isActive: boolean) {
    try {
      setSavingUserId(userId);
      const updated = await usersApi.update(userId, { is_active: isActive });
      setUsers((current) => current.map((user) => (user.id === userId ? updated : user)));
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось обновить статус пользователя."));
    } finally {
      setSavingUserId(null);
    }
  }

  async function handleDeleteUser() {
    if (!userPendingDeletion) {
      return;
    }

    const userId = userPendingDeletion.id;
    try {
      setSavingUserId(userId);
      setError(null);
      await usersApi.delete(userId);
      setUsers((current) => current.filter((user) => user.id !== userId));
      setUserPendingDeletion(null);

      if (currentUser?.id === userId) {
        logout();
        navigate("/login", { replace: true });
      }
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить пользователя."));
    } finally {
      setSavingUserId(null);
    }
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка пользователей" />;
  }

  return (
    <section className="space-y-6">
      <header className="glass-panel rounded-[32px] border border-black/10 p-8 shadow-panel">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-ember">Администрирование</p>
        <h2 className="mt-3 text-3xl font-extrabold text-ink sm:text-4xl">Управление пользователями</h2>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-ink/70">
          Меняйте глобальные роли и включайте или отключайте аккаунты. Роли
          внутри проектов настраиваются отдельно в каждом проекте.
        </p>
        {error ? (
          <p aria-live="polite" className="mt-4 rounded-2xl bg-ember/10 px-4 py-3 text-sm text-ember">
            {error}
          </p>
        ) : null}
      </header>

      <div className="space-y-4">
        {users.map((user) => (
          <article
            key={user.id}
            className="glass-panel rounded-[18px] border border-black/10 p-5 shadow-panel"
          >
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h3 className="text-xl font-bold text-ink">{user.full_name}</h3>
                <p className="text-sm text-ink/60">{user.email}</p>
              </div>

              <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] lg:w-[40rem]">
                <select
                  aria-label={`Глобальная роль для ${user.full_name}`}
                  className="ui-field"
                  disabled={savingUserId === user.id}
                  onChange={(event) => void handleRoleChange(user.id, event.target.value as UserRole)}
                  value={user.role}
                >
                  {ROLE_OPTIONS.map((role) => (
                    <option key={role} value={role}>
                      {getRoleLabel(role)}
                    </option>
                  ))}
                </select>

                <label className="flex items-center justify-between rounded-2xl border border-black/10 bg-white px-4 py-3 text-sm text-ink">
                  <span>{user.is_active ? "Активен" : "Отключён"}</span>
                  <input
                    aria-label={`${user.is_active ? "Отключить" : "Активировать"} ${user.full_name}`}
                    checked={user.is_active}
                    disabled={savingUserId === user.id}
                    onChange={(event) => void handleActiveToggle(user.id, event.target.checked)}
                    type="checkbox"
                  />
                </label>

                <button
                  className="ui-button-danger"
                  disabled={savingUserId === user.id}
                  onClick={() => setUserPendingDeletion(user)}
                  type="button"
                >
                  Удалить
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>

      <ConfirmDialog
        busy={savingUserId === userPendingDeletion?.id}
        confirmLabel="Удалить"
        description={
          userPendingDeletion
            ? `Аккаунт ${userPendingDeletion.email} будет отключён, персональные данные профиля будут очищены, а все активные сессии завершены.`
            : ""
        }
        destructive
        onClose={() => setUserPendingDeletion(null)}
        onConfirm={() => void handleDeleteUser()}
        open={userPendingDeletion !== null}
        title="Удалить пользователя?"
      />
    </section>
  );
}
