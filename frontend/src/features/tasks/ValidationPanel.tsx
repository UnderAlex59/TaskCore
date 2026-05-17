import { useEffect, useMemo, useState } from "react";

import type { ValidationResult } from "@/api/tasksApi";
import { getValidationVerdictLabel } from "@/shared/lib/locale";

interface Props {
  blockedReason?: string;
  canAppeal?: boolean;
  canValidate?: boolean;
  onAppeal?: (
    items: Array<{ finding_id: string; reason: string }>,
  ) => Promise<void>;
  onValidate?: () => Promise<void>;
  appealing?: boolean;
  requiresRevalidation?: boolean;
  validating?: boolean;
  result: ValidationResult | null;
}

const SOURCE_LABELS: Record<string, string> = {
  context_questions: "Контекст",
  core_rules: "Базовые правила",
  custom_rules: "Правила проекта",
};

function getQuestionText(question: ValidationResult["questions"][number]) {
  if (typeof question === "string") {
    const trimmed = question.trim();
    if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
      const match = trimmed.match(
        /['"](?:message|question|text|content)['"]\s*:\s*['"]([^'"]+)['"]/,
      );
      return match?.[1]?.trim() || trimmed;
    }
    return trimmed;
  }

  return (
    question.message?.trim() ||
    question.question?.trim() ||
    question.text?.trim() ||
    question.content?.trim() ||
    ""
  );
}

export default function ValidationPanel({
  appealing = false,
  blockedReason,
  canAppeal = false,
  result,
  onAppeal,
  canValidate = false,
  onValidate,
  requiresRevalidation = false,
  validating = false,
}: Props) {
  const [selectedFindings, setSelectedFindings] = useState<
    Record<string, boolean>
  >({});
  const [appealReasons, setAppealReasons] = useState<Record<string, string>>(
    {},
  );

  const blockingIssues = useMemo(
    () =>
      (result?.issues ?? []).map((issue, index) => ({
        ...issue,
        finding_id:
          issue.finding_id?.trim() || `${issue.source ?? "legacy"}-${issue.code}-${index}`,
      })),
    [result?.issues],
  );
  const appealableIssueIds = blockingIssues.map((issue) => issue.finding_id);
  const canSubmitAppeal =
    Boolean(onAppeal) &&
    appealableIssueIds.length > 0 &&
    appealableIssueIds.every(
      (findingId) =>
        selectedFindings[findingId] &&
        (appealReasons[findingId] ?? "").trim().length >= 3,
    );

  useEffect(() => {
    setSelectedFindings({});
    setAppealReasons({});
  }, [result?.validated_at, result?.verdict]);

  if (!result) {
    return (
      <div className="rounded-[16px] border border-dashed border-[rgba(9,30,66,0.12)] bg-white p-5">
        <p className="text-sm font-semibold text-[#172b4d]">
          Результат проверки
        </p>
        <p className="mt-2 text-sm leading-7 text-[#626f86]">
          Проверка еще не запускалась.
        </p>
        {canValidate && onValidate ? (
          <button
            className="ui-button-primary mt-4"
            disabled={validating}
            onClick={() => void onValidate()}
            type="button"
          >
            {validating ? "Запускаем..." : "Запустить проверку"}
          </button>
        ) : null}
      </div>
    );
  }

  const questions = result.questions.map(getQuestionText).filter(Boolean);
  const appealItems = result.appeal?.items ?? [];

  function handleAppealSubmit() {
    if (!onAppeal || !canSubmitAppeal) {
      return;
    }

    void onAppeal(
      appealableIssueIds.map((findingId) => ({
        finding_id: findingId,
        reason: (appealReasons[findingId] ?? "").trim(),
      })),
    );
  }

  return (
    <div className="rounded-[16px] border border-[rgba(9,30,66,0.1)] bg-white p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
        {getValidationVerdictLabel(result.verdict)}
      </p>

      {blockingIssues.length > 0 ? (
        <ul className="mt-3 space-y-2 text-sm text-[#44546f]">
          {blockingIssues.map((issue) => (
            <li
              key={issue.finding_id}
              className="rounded-[12px] border border-[rgba(172,107,8,0.16)] bg-[#fff4e5] px-3 py-2"
            >
              <span className="font-medium text-[#172b4d]">
                {SOURCE_LABELS[issue.source ?? ""] ?? "Проверка"}:
              </span>{" "}
              {issue.message}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-[#216e1f]">
          Блокирующих проблем не обнаружено.
        </p>
      )}

      {questions.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
            Открытые вопросы
          </p>
          <ul className="mt-2 space-y-2 text-sm text-[#44546f]">
            {questions.map((question, index) => (
              <li key={`${question}-${index}`}>{question}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {canAppeal &&
      onAppeal &&
      result.verdict === "needs_rework" &&
      blockingIssues.length > 0 ? (
        <div className="mt-5 border-t border-[rgba(9,30,66,0.1)] pt-4">
          <p className="text-sm font-semibold text-[#172b4d]">Апелляция</p>
          <div className="mt-3 space-y-3">
            {blockingIssues.map((issue) => {
              const checked = Boolean(selectedFindings[issue.finding_id]);
              return (
                <div
                  key={issue.finding_id}
                  className="rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-3"
                >
                  <label className="flex items-start gap-3 text-sm text-[#172b4d]">
                    <input
                      checked={checked}
                      className="mt-1"
                      onChange={(event) =>
                        setSelectedFindings((current) => ({
                          ...current,
                          [issue.finding_id]: event.target.checked,
                        }))
                      }
                      type="checkbox"
                    />
                    <span>{issue.message}</span>
                  </label>
                  <label className="mt-3 block">
                    <span className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                      Причина отклонения
                    </span>
                    <textarea
                      className="ui-field min-h-[88px] resize-y"
                      disabled={!checked || appealing}
                      onChange={(event) =>
                        setAppealReasons((current) => ({
                          ...current,
                          [issue.finding_id]: event.target.value,
                        }))
                      }
                      value={appealReasons[issue.finding_id] ?? ""}
                    />
                  </label>
                </div>
              );
            })}
          </div>
          <button
            className="ui-button-primary mt-4 w-full"
            disabled={!canSubmitAppeal || appealing}
            onClick={handleAppealSubmit}
            type="button"
          >
            {appealing ? "Сохраняем апелляцию..." : "Отклонить рекомендации"}
          </button>
        </div>
      ) : null}

      {appealItems.length > 0 ? (
        <div className="mt-5 border-t border-[rgba(9,30,66,0.1)] pt-4">
          <p className="text-sm font-semibold text-[#172b4d]">
            Пропущенные замечания системы
          </p>
          <ul className="mt-3 space-y-2 text-sm text-[#44546f]">
            {appealItems.map((item) => (
              <li
                key={item.finding_id}
                className="rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] px-3 py-2"
              >
                <span className="font-medium text-[#172b4d]">
                  {SOURCE_LABELS[item.source ?? ""] ?? "Проверка"}:
                </span>{" "}
                {item.message}
                <span className="mt-1 block text-[#626f86]">
                  Причина: {item.reason}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {requiresRevalidation ? (
        <div className="mt-4 rounded-[12px] border border-[rgba(12,102,228,0.16)] bg-[#e9f2ff] px-3 py-2 text-sm leading-6 text-[#0c66e4]">
          После апрува в задачу внесены изменения. Перед повторной проверкой
          должна быть опубликована версия с пересчитанными эмбеддингами.
        </div>
      ) : null}

      {blockedReason ? (
        <p className="mt-3 text-sm leading-6 text-[#626f86]">{blockedReason}</p>
      ) : null}

      {canValidate && onValidate ? (
        <button
          className="ui-button-secondary mt-4"
          disabled={validating}
          onClick={() => void onValidate()}
          type="button"
        >
          {validating ? "Запускаем..." : "Запустить повторно"}
        </button>
      ) : null}
    </div>
  );
}
