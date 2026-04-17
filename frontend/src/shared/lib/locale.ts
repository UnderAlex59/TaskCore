import type { MonitoringRange, ProviderKind } from "@/api/adminApi";
import type { UserRole } from "@/api/authApi";
import type { TaskStatus, ValidationResult } from "@/api/tasksApi";

const LOCALE = "ru-RU";

const ROLE_LABELS: Record<UserRole, string> = {
  ADMIN: "Администратор",
  ANALYST: "Аналитик",
  DEVELOPER: "Разработчик",
  TESTER: "Тестировщик",
  MANAGER: "Менеджер",
};

const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  draft: "Черновик",
  validating: "Проверяется",
  needs_rework: "Нужна доработка",
  awaiting_approval: "Ожидает подтверждения",
  ready_for_dev: "Готово к разработке",
  in_progress: "В работе",
  done: "Готово",
};

const VERDICT_LABELS: Record<ValidationResult["verdict"], string> = {
  approved: "Проверка пройдена",
  needs_rework: "Нужна доработка",
};

const PROPOSAL_STATUS_LABELS: Record<string, string> = {
  accepted: "Принято",
  new: "Новое",
  rejected: "Отклонено",
};

const PROVIDER_KIND_LABELS: Record<ProviderKind, string> = {
  gigachat: "GigaChat",
  ollama: "Ollama",
  openai: "OpenAI",
  openai_compatible: "Совместимый с OpenAI API",
  openrouter: "OpenRouter",
};

const AGENT_KEY_LABELS: Record<string, string> = {
  "change-tracker": "Трекер изменений",
  manager: "Маршрутизатор",
  qa: "Агент вопросов",
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  "admin.llm_override.updated": "Обновлено правило маршрутизации агента",
  "admin.llm_provider.created": "Создан профиль провайдера",
  "admin.llm_provider.default_set": "Изменён провайдер по умолчанию",
  "admin.llm_provider.tested": "Проверено подключение к провайдеру",
  "admin.llm_provider.updated": "Обновлён профиль провайдера",
  "auth.login.success": "Успешный вход",
  "auth.logout": "Выход из системы",
  "auth.refresh.success": "Продление сессии",
  "auth.registered": "Регистрация пользователя",
  "auth.session.revoked": "Завершение сессии",
  "chat.message_sent": "Отправлено сообщение",
  "chat.proposal_requested": "Запрошено изменение требования",
  "project.created": "Создан проект",
  "project.deleted": "Удалён проект",
  "project.member_removed": "Участник удалён из проекта",
  "project.member_upserted": "Состав участников проекта обновлён",
  "project.updated": "Проект обновлён",
  "proposal.created": "Создано предложение изменения",
  "proposal.reviewed": "Предложение изменения рассмотрено",
  "rule.created": "Создано правило",
  "rule.deleted": "Удалено правило",
  "rule.updated": "Правило обновлено",
  "task.approved": "Задача подтверждена и команда сформирована",
  "task.attachment_uploaded": "Загружено вложение",
  "task.created": "Создана задача",
  "task.deleted": "Удалена задача",
  "task.updated": "Задача обновлена",
  "task.validated": "Задача проверена",
  "user.updated": "Профиль пользователя обновлён",
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  change_proposal: "предложение изменения",
  custom_rule: "правило",
  llm_override: "маршрутизация агента",
  llm_provider: "LLM-провайдер",
  message: "сообщение",
  project: "проект",
  project_member: "участник проекта",
  session: "сессия",
  task: "задача",
  task_attachment: "вложение задачи",
  user: "пользователь",
};

const RANGE_LABELS: Record<MonitoringRange, string> = {
  "24h": "24 ч",
  "7d": "7 дн",
  "30d": "30 дн",
  "90d": "90 дн",
};

function normalizeFallbackLabel(value: string) {
  return value.replaceAll("_", " ").replaceAll(".", " / ");
}

export function pluralizeRu(
  count: number,
  one: string,
  few: string,
  many: string,
) {
  const mod10 = count % 10;
  const mod100 = count % 100;

  if (mod10 === 1 && mod100 !== 11) {
    return one;
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return few;
  }
  return many;
}

export function formatCountLabel(
  count: number,
  one: string,
  few: string,
  many: string,
) {
  return `${count} ${pluralizeRu(count, one, few, many)}`;
}

export function formatShortDate(value: string) {
  return new Intl.DateTimeFormat(LOCALE, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

export function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(LOCALE, {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
  }).format(new Date(value));
}

export function formatDateTimeFull(value: string) {
  return new Intl.DateTimeFormat(LOCALE, {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

export function formatDateTimeWithSeconds(value: string) {
  return new Intl.DateTimeFormat(LOCALE, {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    second: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

export function formatPercent(value: number) {
  return new Intl.NumberFormat(LOCALE, {
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
    style: "percent",
  }).format(value);
}

export function formatCurrencyUsd(value: number | string | null) {
  if (value === null) {
    return "н/д";
  }

  return new Intl.NumberFormat(LOCALE, {
    currency: "USD",
    maximumFractionDigits: 4,
    minimumFractionDigits: 4,
    style: "currency",
  }).format(Number(value));
}

export function getRoleLabel(role: string | null | undefined) {
  if (!role) {
    return "Роль не указана";
  }

  return ROLE_LABELS[role as UserRole] ?? normalizeFallbackLabel(role);
}

export function getTaskStatusLabel(status: string | null | undefined) {
  if (!status) {
    return "Статус не указан";
  }

  return TASK_STATUS_LABELS[status as TaskStatus] ?? normalizeFallbackLabel(status);
}

export function getValidationVerdictLabel(
  verdict: ValidationResult["verdict"] | string | null | undefined,
) {
  if (!verdict) {
    return "Проверка не выполнялась";
  }

  return (
    VERDICT_LABELS[verdict as ValidationResult["verdict"]] ??
    normalizeFallbackLabel(verdict)
  );
}

export function getProposalStatusLabel(status: string | null | undefined) {
  if (!status) {
    return "Статус не указан";
  }

  return PROPOSAL_STATUS_LABELS[status] ?? normalizeFallbackLabel(status);
}

export function getProviderKindLabel(providerKind: string | null | undefined) {
  if (!providerKind) {
    return "Не указан";
  }

  return PROVIDER_KIND_LABELS[providerKind as ProviderKind] ?? providerKind;
}

export function getMonitoringRangeLabel(range: MonitoringRange) {
  return RANGE_LABELS[range];
}

export function getEventTypeLabel(eventType: string | null | undefined) {
  if (!eventType) {
    return "Неизвестное событие";
  }

  return EVENT_TYPE_LABELS[eventType] ?? normalizeFallbackLabel(eventType);
}

export function getEntityTypeLabel(entityType: string | null | undefined) {
  if (!entityType) {
    return "сущность";
  }

  return ENTITY_TYPE_LABELS[entityType] ?? normalizeFallbackLabel(entityType);
}

export function getAgentKeyLabel(agentKey: string | null | undefined) {
  if (!agentKey) {
    return "Системная проверка";
  }

  return AGENT_KEY_LABELS[agentKey] ?? agentKey;
}
