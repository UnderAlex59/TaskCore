import type { ValidationResult } from "@/api/tasksApi";
import { getValidationVerdictLabel } from "@/shared/lib/locale";

interface Props {
  canValidate?: boolean;
  onValidate?: () => Promise<void>;
  validating?: boolean;
  result: ValidationResult | null;
}

export default function ValidationPanel({
  result,
  canValidate = false,
  onValidate,
  validating = false,
}: Props) {
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

  return (
    <div className="rounded-[16px] border border-[rgba(9,30,66,0.1)] bg-white p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
        {getValidationVerdictLabel(result.verdict)}
      </p>

      {result.issues.length > 0 ? (
        <ul className="mt-3 space-y-2 text-sm text-[#44546f]">
          {result.issues.map((issue) => (
            <li
              key={issue.code}
              className="rounded-[12px] border border-[rgba(172,107,8,0.16)] bg-[#fff4e5] px-3 py-2"
            >
              {issue.message}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-[#216e1f]">
          Блокирующих проблем не обнаружено.
        </p>
      )}

      {result.questions.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
            Открытые вопросы
          </p>
          <ul className="mt-2 space-y-2 text-sm text-[#44546f]">
            {result.questions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </div>
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
