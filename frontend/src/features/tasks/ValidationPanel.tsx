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
      <div className="rounded-[10px] border border-dashed border-black/10 p-5">
        <p className="text-sm font-semibold text-ink">Результат проверки</p>
        <p className="mt-2 text-sm leading-7 text-slate/70">
          Проверка ещё не запускалась.
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
    <div className="rounded-[10px] border border-black/10 bg-white/70 p-5">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
        {getValidationVerdictLabel(result.verdict)}
      </p>
      {result.issues.length > 0 ? (
        <ul className="mt-3 space-y-2 text-sm text-slate/80">
          {result.issues.map((issue) => (
            <li
              key={issue.code}
              className="rounded-[8px] bg-ember/10 px-3 py-2"
            >
              {issue.message}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-pine">
          Блокирующих проблем не обнаружено.
        </p>
      )}
      <ul className="mt-3 space-y-2 text-sm text-slate/75">
        {result.questions.map((question) => (
          <li key={question}>{question}</li>
        ))}
      </ul>
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
