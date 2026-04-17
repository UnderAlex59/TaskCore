const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

interface NameLike {
  email?: string | null;
  full_name?: string | null;
  nickname?: string | null;
}

export function getUserDisplayName(user: NameLike | null | undefined) {
  if (!user) {
    return "Пользователь";
  }

  return (
    user.nickname?.trim() ||
    user.full_name?.trim() ||
    user.email?.trim() ||
    "Пользователь"
  );
}

export function getInitials(value: string) {
  const parts = value
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);

  if (parts.length === 0) {
    return "U";
  }

  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("");
}

export function resolveAssetUrl(path: string | null | undefined) {
  if (!path) {
    return null;
  }
  if (/^(https?:)?\/\//.test(path) || path.startsWith("data:")) {
    return path;
  }
  if (/^https?:\/\//.test(API_BASE)) {
    return new URL(path, API_BASE).toString();
  }
  return path;
}
