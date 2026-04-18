import { useEffect, useId, useRef, useState } from "react";

import type { TaskTagOption } from "@/api/taskTagsApi";

interface Props {
  disabled?: boolean;
  emptyLabel?: string;
  helperText?: string;
  hideLabel?: boolean;
  label: string;
  name: string;
  noOptionsLabel?: string;
  onChange: (value: string[]) => void;
  options: TaskTagOption[];
  placeholder?: string;
  searchPlaceholder?: string;
  value: string[];
}

export default function TagMultiSelect({
  value,
  options,
  onChange,
  label,
  name,
  disabled = false,
  placeholder = "Выберите теги",
  searchPlaceholder = "Поиск тегов",
  emptyLabel = "Ничего не найдено",
  noOptionsLabel = "Справочник тегов пока пуст",
  helperText,
  hideLabel = false,
}: Props) {
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!isOpen) {
      setQuery("");
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [isOpen]);

  const mergedOptions = [...options];
  for (const selectedTag of value) {
    if (!mergedOptions.some((option) => option.name === selectedTag)) {
      mergedOptions.push({ id: `selected-${selectedTag}`, name: selectedTag });
    }
  }

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredOptions = normalizedQuery
    ? mergedOptions.filter((option) =>
        option.name.toLocaleLowerCase().includes(normalizedQuery),
      )
    : mergedOptions;

  function toggleTag(tagName: string) {
    if (disabled) {
      return;
    }

    if (value.includes(tagName)) {
      onChange(value.filter((currentTag) => currentTag !== tagName));
      return;
    }

    onChange([...value, tagName]);
  }

  function removeTag(tagName: string) {
    onChange(value.filter((currentTag) => currentTag !== tagName));
  }

  const summary = value.length === 0 ? placeholder : value.join(", ");

  return (
    <div ref={rootRef} className="block">
      {hideLabel ? null : (
        <span className="mb-2 block text-sm font-semibold text-ink/70">
          {label}
        </span>
      )}
      <div className="relative">
        <button
          aria-label={`${label}: ${summary}`}
          aria-controls={panelId}
          aria-expanded={isOpen}
          className="ui-field flex min-h-[3rem] items-center justify-between gap-4 text-left"
          disabled={disabled}
          name={name}
          onClick={() => setIsOpen((current) => !current)}
          type="button"
        >
          <span className={value.length === 0 ? "text-slate/50" : "text-ink"}>
            {summary}
          </span>
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate/60">
            {isOpen ? "Скрыть" : "Выбрать"}
          </span>
        </button>

        {isOpen ? (
          <div
            id={panelId}
            className="absolute z-20 mt-2 w-full rounded-[12px] border border-black/10 bg-white p-3 shadow-panel"
          >
            <input
              aria-label={`${label}: поиск`}
              autoComplete="off"
              className="ui-field"
              name={`${name}-search`}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchPlaceholder}
              type="search"
              value={query}
            />

            <div className="mt-3 max-h-60 overflow-auto rounded-[10px] border border-black/10 bg-slate-50/50 p-2">
              {mergedOptions.length === 0 ? (
                <p className="px-3 py-4 text-sm text-slate/70">
                  {noOptionsLabel}
                </p>
              ) : filteredOptions.length === 0 ? (
                <p className="px-3 py-4 text-sm text-slate/70">{emptyLabel}</p>
              ) : (
                filteredOptions.map((option) => {
                  const checked = value.includes(option.name);

                  return (
                    <label
                      key={option.id}
                      className="flex cursor-pointer items-center gap-3 rounded-[8px] px-3 py-2 text-sm text-ink transition-colors hover:bg-white"
                    >
                      <input
                        checked={checked}
                        onChange={() => toggleTag(option.name)}
                        type="checkbox"
                      />
                      <span>{option.name}</span>
                    </label>
                  );
                })
              )}
            </div>

            <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate/70">
              <span>Выбрано: {value.length}</span>
              <button
                className="font-semibold text-ember disabled:cursor-not-allowed disabled:text-slate/40"
                disabled={disabled || value.length === 0}
                onClick={() => onChange([])}
                type="button"
              >
                Очистить
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {helperText ? (
        <p className="mt-2 text-xs leading-6 text-slate/70">{helperText}</p>
      ) : null}

      {value.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {value.map((tag) => (
            <button
              aria-label={`Убрать тег ${tag}`}
              key={tag}
              className="rounded-full bg-black/5 px-3 py-1 text-xs font-semibold text-slate/80 transition-colors hover:bg-black/10 disabled:cursor-default disabled:hover:bg-black/5"
              disabled={disabled}
              onClick={() => removeTag(tag)}
              type="button"
            >
              {tag}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
