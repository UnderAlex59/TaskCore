import { startTransition, useState } from "react";

export function useApi<TArgs extends unknown[], TResult>(
  fn: (...args: TArgs) => Promise<TResult>,
) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function execute(...args: TArgs) {
    setLoading(true);
    setError(null);

    try {
      return await fn(...args);
    } catch (caught) {
      const normalized = caught instanceof Error ? caught : new Error("Неизвестная ошибка API");
      startTransition(() => {
        setError(normalized);
      });
      throw normalized;
    } finally {
      setLoading(false);
    }
  }

  return { execute, loading, error };
}
