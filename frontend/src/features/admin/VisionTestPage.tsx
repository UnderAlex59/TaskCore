import { useState } from "react";

import {
  adminApi,
  type VisionTestResult,
} from "@/api/adminApi";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { getProviderKindLabel } from "@/shared/lib/locale";

const DEFAULT_PROMPT =
  "Извлеки весь читаемый текст с изображения. " +
  "Сохрани естественный порядок чтения сверху вниз и слева направо. " +
  "Не пересказывай изображение и не добавляй пояснения от себя. " +
  "Неразборчивые фрагменты помечай как [неразборчиво]. " +
  "Ответ дай простым текстом без Markdown.";

export default function VisionTestPage() {
  const [file, setFile] = useState<File | null>(null);
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [result, setResult] = useState<VisionTestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Выберите изображение для проверки.");
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setResult(await adminApi.testVision(file, prompt));
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось выполнить Vision-тест."),
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-6">
      <header className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-ember">
          Vision Test
        </p>
        <h3 className="mt-2 text-2xl font-extrabold text-ink sm:text-3xl">
          Проверка извлечения текста из изображений
        </h3>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-ink/70">
          Страница прогоняет изображение через текущий LangGraph-узел
          <span className="font-semibold text-ink"> rag-vision </span>
          и показывает фактический ответ модели. Это удобно для проверки OCR,
          alt-text и качества vision-профиля до загрузки вложений в задачи.
        </p>
      </header>

      <div className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <form
          className="glass-panel space-y-5 rounded-[28px] border border-black/10 p-6 shadow-panel"
          onSubmit={handleSubmit}
        >
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
              Входные данные
            </p>
            <h4 className="mt-2 text-2xl font-extrabold text-ink">
              Изображение и промпт
            </h4>
          </div>

          {error ? (
            <p
              aria-live="polite"
              className="rounded-2xl bg-ember/10 px-4 py-3 text-sm text-ember"
            >
              {error}
            </p>
          ) : null}

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Файл изображения
            </span>
            <input
              accept="image/*"
              className="ui-field file:mr-4 file:rounded-xl file:border-0 file:bg-[#e9f2ff] file:px-3 file:py-2 file:text-sm file:font-semibold file:text-[#0c66e4]"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setResult(null);
              }}
              type="file"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Инструкция для модели
            </span>
            <textarea
              className="ui-field min-h-[220px]"
              onChange={(event) => setPrompt(event.target.value)}
              value={prompt}
            />
          </label>

          <div className="rounded-[22px] border border-black/10 bg-white/70 px-4 py-4 text-sm text-ink/65">
            <p className="font-semibold text-ink">
              {file ? file.name : "Файл пока не выбран"}
            </p>
            <p className="mt-1">
              {file
                ? `${file.type || "Неизвестный MIME"} · ${file.size.toLocaleString("ru-RU")} байт`
                : "Поддерживаются обычные image/* MIME-типы. Тест использует текущую конфигурацию rag-vision."}
            </p>
          </div>

          <button
            className={loading ? "ui-button-secondary" : "ui-button-primary"}
            disabled={loading}
            type="submit"
          >
            {loading ? "Выполняем тест..." : "Запустить Vision-тест"}
          </button>
        </form>

        <section className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
              Результат
            </p>
            <h4 className="mt-2 text-2xl font-extrabold text-ink">
              Ответ модели
            </h4>
          </div>

          {!result ? (
            <div className="mt-5 rounded-[24px] border border-dashed border-black/10 bg-white/60 px-5 py-8 text-sm leading-7 text-ink/55">
              После запуска теста здесь появятся метаданные вызова и извлечённый
              текст.
            </div>
          ) : (
            <div className="mt-5 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <article className="rounded-[22px] border border-black/10 bg-white/70 p-4">
                  <p className="text-xs font-bold uppercase tracking-[0.14em] text-ink/45">
                    Профиль
                  </p>
                  <p className="mt-2 text-lg font-bold text-ink">
                    {result.provider_name ?? "Не определён"}
                  </p>
                  <p className="mt-1 text-sm text-ink/65">
                    {getProviderKindLabel(result.provider_kind)} / {result.model}
                  </p>
                </article>
                <article className="rounded-[22px] border border-black/10 bg-white/70 p-4">
                  <p className="text-xs font-bold uppercase tracking-[0.14em] text-ink/45">
                    Статус
                  </p>
                  <p className="mt-2 text-lg font-bold text-ink">
                    {result.ok ? "Успешно" : "Ошибка"}
                  </p>
                  <p className="mt-1 text-sm text-ink/65">
                    {result.latency_ms ? `${result.latency_ms} мс` : "Время не получено"}
                  </p>
                </article>
              </div>

              <article className="rounded-[24px] border border-black/10 bg-white/70 p-5">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-ink/45">
                  Диагностика
                </p>
                <p className="mt-3 text-sm leading-7 text-ink/75">
                  {result.message}
                </p>
              </article>

              <article className="rounded-[24px] border border-black/10 bg-[#f8fafc] p-5">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-bold uppercase tracking-[0.14em] text-ink/45">
                    Извлечённый текст
                  </p>
                  <span className="text-xs text-ink/45">{result.content_type}</span>
                </div>
                <pre className="mt-3 whitespace-pre-wrap break-words font-mono text-sm leading-7 text-ink">
                  {result.result_text ?? "Модель не вернула текст."}
                </pre>
              </article>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}
