import { useState } from "react";

import { usersApi } from "@/api/usersApi";
import { Avatar } from "@/shared/components/Avatar";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { getUserDisplayName } from "@/shared/lib/userProfile";
import { useAuthStore } from "@/store/authStore";

export default function ProfilePage() {
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const [nickname, setNickname] = useState(user?.nickname ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [removingAvatar, setRemovingAvatar] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  if (!user) {
    return null;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      const updatedUser = await usersApi.updateMe({
        nickname,
        current_password: currentPassword || undefined,
        new_password: newPassword || undefined,
      });
      setUser(updatedUser);
      setCurrentPassword("");
      setNewPassword("");
      setSuccess("Профиль обновлён.");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось обновить профиль."));
    } finally {
      setSaving(false);
    }
  }

  async function handleAvatarChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    try {
      setUploading(true);
      setError(null);
      setSuccess(null);
      const updatedUser = await usersApi.uploadAvatar(file);
      setUser(updatedUser);
      setSuccess("Аватар обновлён.");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить аватар."));
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  async function handleRemoveAvatar() {
    try {
      setRemovingAvatar(true);
      setError(null);
      setSuccess(null);
      const updatedUser = await usersApi.updateMe({ remove_avatar: true });
      setUser(updatedUser);
      setSuccess("Аватар удалён.");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить аватар."));
    } finally {
      setRemovingAvatar(false);
    }
  }

  return (
    <section className="space-y-6">
      <header className="glass-panel border border-black/10 p-6 shadow-panel sm:p-8">
        <p className="section-eyebrow">Профиль</p>
        <h2 className="mt-3 text-3xl font-bold text-ink sm:text-4xl">
          Настройки пользователя
        </h2>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-slate/80">
          Здесь можно обновить никнейм, сменить пароль и загрузить аватар, который
          будет показываться в чате.
        </p>
      </header>

      <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="glass-panel border border-black/10 p-6 shadow-panel">
          <div className="flex flex-col items-center text-center">
            <Avatar
              className="h-28 w-28 text-3xl"
              imageUrl={user.avatar_url}
              name={getUserDisplayName(user)}
            />
            <h3 className="mt-4 text-2xl font-bold text-ink">
              {getUserDisplayName(user)}
            </h3>
            <p className="mt-2 break-all text-sm text-slate/70">{user.email}</p>
          </div>

          <div className="mt-6 space-y-3">
            <label className="ui-button-primary flex cursor-pointer items-center justify-center">
              <span>{uploading ? "Загружаем..." : "Загрузить аватар"}</span>
              <input
                accept="image/*"
                className="hidden"
                disabled={uploading}
                onChange={handleAvatarChange}
                type="file"
              />
            </label>
            <button
              className="ui-button-secondary w-full"
              disabled={removingAvatar || !user.avatar_url}
              onClick={() => void handleRemoveAvatar()}
              type="button"
            >
              {removingAvatar ? "Удаляем..." : "Удалить аватар"}
            </button>
          </div>
        </aside>

        <form
          className="glass-panel space-y-5 border border-black/10 p-6 shadow-panel"
          onSubmit={handleSubmit}
        >
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Никнейм
            </span>
            <input
              className="ui-field"
              maxLength={100}
              onChange={(event) => setNickname(event.target.value)}
              placeholder="Например, Alex"
              value={nickname}
            />
          </label>

          <div className="grid gap-5 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Текущий пароль
              </span>
              <input
                autoComplete="current-password"
                className="ui-field"
                onChange={(event) => setCurrentPassword(event.target.value)}
                type="password"
                value={currentPassword}
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Новый пароль
              </span>
              <input
                autoComplete="new-password"
                className="ui-field"
                onChange={(event) => setNewPassword(event.target.value)}
                type="password"
                value={newPassword}
              />
            </label>
          </div>

          <p className="text-xs leading-6 text-slate/65">
            Если меняете пароль, укажите текущий. Новый пароль должен содержать
            минимум 8 символов, одну заглавную букву и одну цифру.
          </p>

          {error ? (
            <p className="rounded-[10px] bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </p>
          ) : null}
          {success ? (
            <p className="rounded-[10px] bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {success}
            </p>
          ) : null}

          <button className="ui-button-primary" disabled={saving} type="submit">
            {saving ? "Сохраняем..." : "Сохранить профиль"}
          </button>
        </form>
      </div>
    </section>
  );
}
