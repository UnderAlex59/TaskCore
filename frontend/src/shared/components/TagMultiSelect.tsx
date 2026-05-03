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
    <div ref={rootRef} className="block min-w-0">
      {hideLabel ? null : (
        <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
          {label}
        </span>
      )}

      <div className="relative min-w-0">
        <button
          aria-label={`${label}: ${summary}`}
          aria-controls={panelId}
          aria-expanded={isOpen}
          className="ui-field flex min-h-[3rem] min-w-0 items-center justify-between gap-4 text-left"
          disabled={disabled}
          name={name}
          onClick={() => setIsOpen((current) => !current)}
          type="button"
        >
          <span
            className={
              value.length === 0
                ? "min-w-0 text-anywhere text-[#7a869a]"
                : "min-w-0 text-anywhere text-[#172b4d]"
            }
          >
            {summary}
          </span>
          <span className="shrink-0 text-xs font-semibold uppercase tracking-[0.12em] text-[#626f86]">
            {isOpen ? "Скрыть" : "Выбрать"}
          </span>
        </button>

        {isOpen ? (
          <div
            id={panelId}
            className="absolute z-20 mt-2 w-full min-w-0 rounded-[14px] border border-[rgba(9,30,66,0.12)] bg-white p-3 shadow-[0_12px_24px_rgba(9,30,66,0.08)]"
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

            <div className="mt-3 max-h-60 overflow-auto rounded-[12px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] p-2">
              {mergedOptions.length === 0 ? (
                <p className="px-3 py-4 text-sm text-[#626f86]">
                  {noOptionsLabel}
                </p>
              ) : filteredOptions.length === 0 ? (
                <p className="px-3 py-4 text-sm text-[#626f86]">{emptyLabel}</p>
              ) : (
                filteredOptions.map((option) => {
                  const checked = value.includes(option.name);

                  return (
                    <label
                      key={option.id}
                      className="flex min-w-0 cursor-pointer items-center gap-3 rounded-[10px] px-3 py-2 text-sm text-[#172b4d] transition-colors hover:bg-white"
                    >
                      <input
                        checked={checked}
                        onChange={() => toggleTag(option.name)}
                        type="checkbox"
                      />
                      <span className="text-anywhere min-w-0">
                        {option.name}
                      </span>
                    </label>
                  );
                })
              )}
            </div>

            <div className="mt-3 flex items-center justify-between gap-3 text-xs text-[#626f86]">
              <span>Выбрано: {value.length}</span>
              <button
                className="font-semibold text-[#0c66e4] disabled:cursor-not-allowed disabled:text-[#97a0af]"
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
        <p className="text-anywhere mt-2 text-xs leading-6 text-[#626f86]">
          {helperText}
        </p>
      ) : null}

      {value.length > 0 ? (
        <div className="mt-3 flex min-w-0 flex-wrap gap-2">
          {value.map((tag) => (
            <button
              aria-label={`Убрать тег ${tag}`}
              key={tag}
              className="text-anywhere max-w-full rounded-full border border-[rgba(9,30,66,0.08)] bg-[#f7f8fa] px-3 py-1 text-xs font-semibold text-[#44546f] transition-colors hover:bg-[#eef0f3] disabled:cursor-default disabled:hover:bg-[#f7f8fa]"
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
