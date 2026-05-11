import { useEffect, useState } from "react";

import {
  notificationsApi,
  type NotificationSettingsRead,
} from "@/api/notificationsApi";
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
  const [notificationSettings, setNotificationSettings] =
    useState<NotificationSettingsRead | null>(null);
  const [telegramDeepLink, setTelegramDeepLink] = useState<string | null>(null);
  const [telegramTokenExpiresAt, setTelegramTokenExpiresAt] = useState<
    string | null
  >(null);
  const [telegramBusy, setTelegramBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void notificationsApi.getSettings().then((settings) => {
      if (active) {
        setNotificationSettings(settings);
      }
    });

    return () => {
      active = false;
    };
  }, []);

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
      setSuccess("Профиль обновлен.");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось обновить профиль."));
    } finally {
      setSaving(false);
    }
  }

  async function handleAvatarChange(
    event: React.ChangeEvent<HTMLInputElement>,
  ) {
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
      setSuccess("Аватар обновлен.");
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
      setSuccess("Аватар удален.");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить аватар."));
    } finally {
      setRemovingAvatar(false);
    }
  }

  async function handleCreateTelegramToken() {
    try {
      setTelegramBusy(true);
      setError(null);
      setSuccess(null);
      const token = await notificationsApi.createTelegramLinkToken();
      setTelegramDeepLink(token.deep_link);
      setTelegramTokenExpiresAt(token.expires_at);
      if (token.deep_link) {
        setSuccess("Ссылка для привязки Telegram создана.");
      } else {
        setError(
          "TELEGRAM_BOT_USERNAME не настроен на backend. Обратитесь к администратору.",
        );
      }
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось создать ссылку для Telegram."),
      );
    } finally {
      setTelegramBusy(false);
    }
  }

  async function handleToggleTelegramSetting(
    key: "telegram_important_enabled" | "telegram_normal_enabled",
    enabled: boolean,
  ) {
    try {
      setTelegramBusy(true);
      setError(null);
      const payload =
        key === "telegram_important_enabled"
          ? { telegram_important_enabled: enabled }
          : { telegram_normal_enabled: enabled };
      const settings = await notificationsApi.updateSettings({
        ...payload,
      });
      setNotificationSettings(settings);
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось обновить настройки уведомлений.",
        ),
      );
    } finally {
      setTelegramBusy(false);
    }
  }

  async function handleUnlinkTelegram() {
    try {
      setTelegramBusy(true);
      setError(null);
      await notificationsApi.unlinkTelegram();
      setTelegramDeepLink(null);
      setTelegramTokenExpiresAt(null);
      setNotificationSettings(await notificationsApi.getSettings());
      setSuccess("Telegram отключен.");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось отключить Telegram."));
    } finally {
      setTelegramBusy(false);
    }
  }

  return (
    <section className="space-y-6">
      <header className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-6 sm:px-8">
        <p className="section-eyebrow">Профиль</p>
        <h2 className="mt-3 text-3xl font-semibold text-[#172b4d] sm:text-4xl">
          Настройки пользователя
        </h2>
      </header>

      <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white p-6">
          <div className="flex flex-col items-center text-center">
            <Avatar
              className="h-28 w-28 text-3xl"
              imageUrl={user.avatar_url}
              name={getUserDisplayName(user)}
            />
            <h3 className="mt-4 text-2xl font-semibold text-[#172b4d]">
              {getUserDisplayName(user)}
            </h3>
            <p className="mt-2 break-all text-sm text-[#44546f]">
              {user.email}
            </p>
          </div>

          <div className="mt-6 space-y-3">
            <label className="ui-button-secondary flex cursor-pointer items-center justify-center">
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
              className="ui-button-ghost w-full justify-center"
              disabled={removingAvatar || !user.avatar_url}
              onClick={() => void handleRemoveAvatar()}
              type="button"
            >
              {removingAvatar ? "Удаляем..." : "Удалить аватар"}
            </button>
          </div>
        </aside>

        <form
          className="space-y-5 rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white p-6"
          onSubmit={handleSubmit}
        >
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
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
              <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
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
              <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
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

          {error ? (
            <p className="rounded-[12px] border border-[rgba(174,46,36,0.18)] bg-[#fdecec] px-4 py-3 text-sm text-[#ae2e24]">
              {error}
            </p>
          ) : null}
          {success ? (
            <p className="rounded-[12px] border border-[rgba(34,154,22,0.14)] bg-[#e8f5e9] px-4 py-3 text-sm text-[#216e1f]">
              {success}
            </p>
          ) : null}

          <button className="ui-button-primary" disabled={saving} type="submit">
            {saving ? "Сохраняем..." : "Сохранить профиль"}
          </button>
        </form>

        <section className="space-y-5 rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white p-6 xl:col-start-2">
          <div>
            <p className="section-eyebrow">Telegram</p>
            <h3 className="mt-2 text-2xl font-semibold text-[#172b4d]">
              Уведомления в Telegram
            </h3>
          </div>

          <div className="rounded-[14px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] px-4 py-3 text-sm leading-7 text-[#44546f]">
            {notificationSettings?.telegram_linked ? (
              <p>
                Telegram подключен
                {notificationSettings.telegram_username
                  ? `: @${notificationSettings.telegram_username}`
                  : "."}
              </p>
            ) : (
              <p>Telegram пока не подключен.</p>
            )}
          </div>

          <label className="flex items-start gap-3 text-sm leading-6 text-[#44546f]">
            <input
              checked={
                notificationSettings?.telegram_important_enabled ?? true
              }
              className="mt-1 h-4 w-4"
              disabled={telegramBusy}
              onChange={(event) =>
                void handleToggleTelegramSetting(
                  "telegram_important_enabled",
                  event.target.checked,
                )
              }
              type="checkbox"
            />
            <span>Отправлять важные уведомления в Telegram</span>
          </label>

          <label className="flex items-start gap-3 text-sm leading-6 text-[#44546f]">
            <input
              checked={notificationSettings?.telegram_normal_enabled ?? true}
              className="mt-1 h-4 w-4"
              disabled={telegramBusy}
              onChange={(event) =>
                void handleToggleTelegramSetting(
                  "telegram_normal_enabled",
                  event.target.checked,
                )
              }
              type="checkbox"
            />
            <span>Отправлять обычные уведомления в Telegram</span>
          </label>

          {telegramDeepLink ? (
            <div className="rounded-[14px] border border-[rgba(12,102,228,0.16)] bg-[#e9f2ff] px-4 py-3">
              <p className="text-sm font-semibold text-[#172b4d]">
                Ссылка привязки
              </p>
              <a
                className="text-anywhere mt-2 block font-mono text-sm font-semibold text-[#0c66e4] underline"
                href={telegramDeepLink}
                rel="noreferrer"
                target="_blank"
              >
                {telegramDeepLink}
              </a>
              <p className="mt-2 text-sm leading-6 text-[#44546f]">
                Откройте ссылку и запустите бота. Ссылка действует до{" "}
                {telegramTokenExpiresAt
                  ? new Date(telegramTokenExpiresAt).toLocaleTimeString(
                      "ru-RU",
                      {
                        hour: "2-digit",
                        minute: "2-digit",
                      },
                    )
                  : "истечения срока"}
                .
              </p>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <button
              className="ui-button-primary"
              disabled={telegramBusy}
              onClick={() => void handleCreateTelegramToken()}
              type="button"
            >
              {telegramBusy ? "Готовим..." : "Получить ссылку"}
            </button>
            <button
              className="ui-button-secondary"
              disabled={telegramBusy || !notificationSettings?.telegram_linked}
              onClick={() => void handleUnlinkTelegram()}
              type="button"
            >
              Отключить Telegram
            </button>
          </div>
        </section>
      </div>
    </section>
  );
}
