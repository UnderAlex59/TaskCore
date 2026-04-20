export type TaskDocumentSectionKey =
  | "description"
  | "businessRules"
  | "acceptanceCriteria"
  | "materials"
  | "changeHistory";

export interface TaskDocumentSections {
  description: string;
  businessRules: string;
  acceptanceCriteria: string;
  materials: string;
  changeHistory: string;
}

export const TASK_DOCUMENT_SECTIONS: Array<{
  key: TaskDocumentSectionKey;
  title: string;
  placeholder: string;
  helperText: string;
}> = [
  {
    key: "description",
    title: "Описание",
    placeholder:
      "Опишите цель задачи, контекст, пользователя и ожидаемый результат.",
    helperText:
      "Кратко и предметно: что меняется, для кого и какую проблему решаем.",
  },
  {
    key: "businessRules",
    title: "Бизнес-правила",
    placeholder:
      "Перечислите ограничения, сценарии, зависимости и правила поведения системы.",
    helperText:
      "Здесь лучше фиксировать инварианты, исключения и важные условия.",
  },
  {
    key: "acceptanceCriteria",
    title: "Acceptance criteria",
    placeholder:
      "Опишите проверяемые критерии приемки в формате списка или коротких сценариев.",
    helperText:
      "Критерии должны быть однозначными и пригодными для тестирования.",
  },
  {
    key: "materials",
    title: "Материалы",
    placeholder:
      "Ссылки на макеты, документы, исследования, внешние зависимости и артефакты.",
    helperText:
      "Используйте этот блок для ссылок и пояснений, а файлы прикладывайте ниже.",
  },
  {
    key: "changeHistory",
    title: "История изменений",
    placeholder:
      "Фиксируйте смысловые правки постановки: что изменилось, когда и почему.",
    helperText:
      "Этот блок помогает команде понять, какие договоренности появились после старта работы.",
  },
];

const SECTION_TITLES: Record<string, TaskDocumentSectionKey> = {
  Описание: "description",
  "Бизнес-правила": "businessRules",
  "Acceptance criteria": "acceptanceCriteria",
  Материалы: "materials",
  "История изменений": "changeHistory",
};

const MAIN_TASK_SECTION_KEYS: TaskDocumentSectionKey[] = [
  "description",
  "businessRules",
  "acceptanceCriteria",
  "materials",
];

export function createEmptyTaskDocument(): TaskDocumentSections {
  return {
    description: "",
    businessRules: "",
    acceptanceCriteria: "",
    materials: "",
    changeHistory: "",
  };
}

function normalizeSectionText(value: string) {
  return value.replaceAll("\r\n", "\n").trim();
}

export function parseTaskDocument(content: string): TaskDocumentSections {
  const normalizedContent = content.replaceAll("\r\n", "\n").trim();
  if (!normalizedContent) {
    return createEmptyTaskDocument();
  }

  const headingPattern =
    /^##\s+(Описание|Бизнес-правила|Acceptance criteria|Материалы|История изменений)\s*$/gm;
  const matches = [...normalizedContent.matchAll(headingPattern)];

  if (matches.length === 0) {
    return {
      ...createEmptyTaskDocument(),
      description: normalizedContent,
    };
  }

  const sections = createEmptyTaskDocument();
  const prefix = normalizedContent.slice(0, matches[0]?.index ?? 0).trim();
  if (prefix) {
    sections.description = prefix;
  }

  for (let index = 0; index < matches.length; index += 1) {
    const currentMatch = matches[index];
    const nextMatch = matches[index + 1];
    const title = currentMatch[1];
    const key = SECTION_TITLES[title];
    if (!key) {
      continue;
    }

    const sectionStart = (currentMatch.index ?? 0) + currentMatch[0].length;
    const sectionEnd = nextMatch?.index ?? normalizedContent.length;
    const rawValue = normalizedContent.slice(sectionStart, sectionEnd).trim();
    sections[key] = sections[key]
      ? `${sections[key]}\n\n${rawValue}`.trim()
      : rawValue;
  }

  return sections;
}

export function serializeTaskDocument(sections: TaskDocumentSections) {
  return TASK_DOCUMENT_SECTIONS.map((section) => {
    const value = normalizeSectionText(sections[section.key]);
    return `## ${section.title}\n${value}`;
  })
    .join("\n\n")
    .trim();
}

export function serializeTaskBodyForEditor(sections: TaskDocumentSections) {
  const normalizedDescription = normalizeSectionText(sections.description);
  const hasStructuredMainSections = MAIN_TASK_SECTION_KEYS.some((key) =>
    key === "description"
      ? false
      : Boolean(normalizeSectionText(sections[key])),
  );

  if (!hasStructuredMainSections) {
    return normalizedDescription;
  }

  return TASK_DOCUMENT_SECTIONS.filter(
    (section) => section.key !== "changeHistory",
  )
    .map((section) => {
      const value = normalizeSectionText(sections[section.key]);
      return `## ${section.title}\n${value}`;
    })
    .join("\n\n")
    .trim();
}

export function buildTaskDocumentFromEditors(
  body: string,
  changeHistory: string,
) {
  const parsed = parseTaskDocument(body);

  return serializeTaskDocument({
    description: parsed.description,
    businessRules: parsed.businessRules,
    acceptanceCriteria: parsed.acceptanceCriteria,
    materials: parsed.materials,
    changeHistory,
  });
}

export function normalizeTaskEditorValue(value: string) {
  return value.replaceAll("\r\n", "\n").trim();
}

export function areTaskDocumentSectionsEqual(
  left: TaskDocumentSections,
  right: TaskDocumentSections,
) {
  return TASK_DOCUMENT_SECTIONS.every(
    (section) =>
      normalizeSectionText(left[section.key]) ===
      normalizeSectionText(right[section.key]),
  );
}
