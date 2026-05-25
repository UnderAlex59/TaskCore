import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  adminApi,
  type AgentPromptConfigRead,
  type AgentPromptVersionRead,
  type ProviderConfigRead,
  type ValidationEvalCasePayload,
  type ValidationEvalCaseRead,
  type ValidationEvalCaseResultRead,
  type ValidationEvalCustomRule,
  type ValidationEvalDatasetDetailRead,
  type ValidationEvalDatasetRead,
  type ValidationEvalExportArtifact,
  type ValidationEvalExpectedIssue,
  type ValidationEvalImportFormat,
  type ValidationEvalRunConfig,
  type ValidationEvalRunListItemRead,
  type ValidationEvalRunPageRead,
  type ValidationEvalRunRead,
  type ValidationEvalRunStatus,
  type ValidationEvalVariantConfig,
  type ValidationEvalVerdict,
} from "@/api/adminApi";
import { projectsApi, type ProjectRead } from "@/api/projectsApi";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import {
  formatDateTimeFull,
  getProviderKindLabel,
  getValidationVerdictLabel,
} from "@/shared/lib/locale";

type ValidationEvalTab = "import" | "datasets" | "cases" | "run" | "results";
type RunStatusFilter = ValidationEvalRunStatus | "all";
type CaseStatusFilter = ValidationEvalCaseResultRead["status"] | "all";
type ExportFormat = "json" | "csv";

type CaseFormState = {
  attachmentNames: string;
  content: string;
  customRules: string;
  expectedContextQuestions: string;
  expectedIssues: string;
  expectedQuestions: string;
  expectedVerdict: ValidationEvalVerdict;
  externalId: string;
  historicalQuestions: string;
  metadata: string;
  relatedTasks: string;
  tags: string;
  title: string;
};

const TABS: Array<{ key: ValidationEvalTab; label: string }> = [
  { key: "import", label: "Импорт" },
  { key: "datasets", label: "Наборы" },
  { key: "cases", label: "Кейсы" },
  { key: "run", label: "Запуск" },
  { key: "results", label: "Результаты" },
];

const RUN_HISTORY_PAGE_SIZE = 10;

const RUN_STATUS_OPTIONS: Array<{ value: RunStatusFilter; label: string }> = [
  { value: "all", label: "Все статусы" },
  { value: "queued", label: "В очереди" },
  { value: "running", label: "Выполняется" },
  { value: "success", label: "Готово" },
  { value: "error", label: "Ошибка" },
];

const CASE_STATUS_OPTIONS: Array<{ value: CaseStatusFilter; label: string }> = [
  { value: "all", label: "Все результаты" },
  { value: "passed", label: "Passed" },
  { value: "failed", label: "Failed" },
  { value: "error", label: "Error" },
];

const EXPORT_ARTIFACTS: Array<{
  label: string;
  value: ValidationEvalExportArtifact;
}> = [
  { value: "case_results", label: "Case results" },
  { value: "metrics", label: "Metrics" },
  { value: "confusion_matrix", label: "Confusion matrix" },
  { value: "ablation", label: "Ablation" },
  { value: "errors", label: "Errors" },
];

type ValidationEvalLevelKey =
  | "core_rules"
  | "custom_rules"
  | "context_questions";

const VALIDATION_LEVEL_VARIANTS: Array<
  ValidationEvalVariantConfig & {
    description: string;
    key: ValidationEvalLevelKey;
  }
> = [
  {
    key: "core_rules",
    label: "Базовые правила",
    description: "Проверка универсальных требований к качеству задачи.",
    provider_config_id: null,
    prompt_version_ids: {},
    validation_node_settings: {
      context_questions: false,
      core_rules: true,
      custom_rules: false,
    },
  },
  {
    key: "custom_rules",
    label: "Правила проекта",
    description: "Проверка требований по custom rules выбранного проекта.",
    provider_config_id: null,
    prompt_version_ids: {},
    validation_node_settings: {
      context_questions: false,
      core_rules: false,
      custom_rules: true,
    },
  },
  {
    key: "context_questions",
    label: "Проектные вопросы",
    description: "Проверка вопросов из исторического проектного контекста.",
    provider_config_id: null,
    prompt_version_ids: {},
    validation_node_settings: {
      context_questions: true,
      core_rules: false,
      custom_rules: false,
    },
  },
];

function makeLevelVariant(
  levelKey: ValidationEvalLevelKey,
  current?: ValidationEvalVariantConfig,
): ValidationEvalVariantConfig {
  const level = VALIDATION_LEVEL_VARIANTS.find((item) => item.key === levelKey);
  const fallback = VALIDATION_LEVEL_VARIANTS[0];
  const selected = level ?? fallback;
  return {
    key: selected.key,
    label: selected.label,
    provider_config_id: current?.provider_config_id ?? null,
    prompt_version_ids: { ...(current?.prompt_version_ids ?? {}) },
    validation_node_settings: { ...selected.validation_node_settings },
  };
}

const DEFAULT_CONFIG: ValidationEvalRunConfig = {
  judge_provider_config_ids: [],
  run_question_judge: true,
  variants: [makeLevelVariant("core_rules")],
};

const EMPTY_CASE_FORM: CaseFormState = {
  attachmentNames: "",
  content: "",
  customRules: "[]",
  expectedContextQuestions: "",
  expectedIssues: "[]",
  expectedQuestions: "",
  expectedVerdict: "needs_rework",
  externalId: "",
  historicalQuestions: "",
  metadata: "{}",
  relatedTasks: "[]",
  tags: "",
  title: "",
};

const JSON_TEMPLATE = `{
  "dataset_name": "Validation eval set",
  "project_id": "project-id",
  "cases": [
    {
      "external_id": "validation-auth-1",
      "title": "Авторизация",
      "content": "Нужно описать вход по email и восстановление пароля.",
      "tags": ["auth", "security"],
      "attachment_names": ["auth-requirements.md"],
      "custom_rules": [
        {
          "title": "Указывать роли",
          "description": "Для задач авторизации нужно явно перечислять роли пользователей.",
          "applies_to_tags": ["auth"]
        }
      ],
      "related_tasks": [
        {
          "external_id": "auth-history-1",
          "title": "Прошлая задача авторизации",
          "content": "Исторический контекст."
        }
      ],
      "historical_questions": [
        "Какие роли должны входить в систему?"
      ],
      "expected_verdict": "needs_rework",
      "expected_issues": [
        {
          "code": "missing_roles",
          "severity": "medium",
          "message": "Не указаны роли пользователей.",
          "rule_title": "Указывать роли",
          "source": "custom_rule"
        }
      ],
      "expected_questions": [
        "Какие роли пользователей должны поддерживаться?"
      ],
      "expected_context_questions": [
        "Какие ограничения из прошлых задач нужно учесть?"
      ],
      "metadata": {
        "chapter": "validation-ablation"
      }
    }
  ]
}`;

const CSV_TEMPLATE = `case_external_id,title,content,tags,attachment_names,custom_rules,related_tasks,historical_questions,expected_verdict,expected_issues,expected_questions,expected_context_questions,metadata
validation-auth-1,Авторизация,Нужно описать вход по email и восстановление пароля.,auth;security,auth-requirements.md,"[{""title"":""Указывать роли"",""description"":""Для задач авторизации нужно явно перечислять роли пользователей."",""applies_to_tags"":[""auth""]}]",[],Какие роли должны входить в систему?,needs_rework,"[{""code"":""missing_roles"",""severity"":""medium"",""message"":""Не указаны роли пользователей."",""rule_title"":""Указывать роли"",""source"":""custom_rule""}]",Какие роли пользователей должны поддерживаться?,Какие ограничения из прошлых задач нужно учесть?,"{""chapter"":""validation-ablation""}"`;

function statusLabel(status: string | null | undefined) {
  switch (status) {
    case "queued":
      return "В очереди";
    case "running":
      return "Выполняется";
    case "success":
      return "Готово";
    case "error":
      return "Ошибка";
    case "passed":
      return "Passed";
    case "failed":
      return "Failed";
    default:
      return "н/д";
  }
}

function metricValue(value: unknown) {
  if (typeof value === "number") {
    if (value > 0 && value <= 1) {
      return `${Math.round(value * 1000) / 10}%`;
    }
    return value.toLocaleString("ru-RU");
  }
  if (value === null || value === undefined || value === "") {
    return "н/д";
  }
  return String(value);
}

function formatMs(value: number | null | undefined) {
  return value === null || value === undefined
    ? "н/д"
    : `${value.toLocaleString("ru-RU")} мс`;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function compactJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function judgeRunsFromGroup(value: unknown): Array<Record<string, unknown>> {
  const group = asRecord(value);
  return Array.isArray(group.judge_runs) ? group.judge_runs.map(asRecord) : [];
}

function normalizedText(value: unknown) {
  return String(value ?? "").toLocaleLowerCase("ru-RU");
}

function shortText(value: unknown, maxLength = 180) {
  const text = String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) {
    return "н/д";
  }
  return text.length > maxLength
    ? `${text.slice(0, maxLength).trim()}...`
    : text;
}

function splitList(value: string) {
  return value
    .split(/[\n,;]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseJsonArray<T>(value: string, label: string): T[] {
  if (!value.trim()) {
    return [];
  }
  const parsed = JSON.parse(value) as unknown;
  if (!Array.isArray(parsed)) {
    throw new Error(`${label}: ожидается JSON-массив.`);
  }
  return parsed as T[];
}

function parseJsonObject(
  value: string,
  label: string,
): Record<string, unknown> {
  if (!value.trim()) {
    return {};
  }
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label}: ожидается JSON-объект.`);
  }
  return parsed as Record<string, unknown>;
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function buildCasePayload(form: CaseFormState): ValidationEvalCasePayload {
  if (!form.externalId.trim()) {
    throw new Error("Укажите external id кейса.");
  }
  if (!form.title.trim()) {
    throw new Error("Укажите название кейса.");
  }

  return {
    attachment_names: splitList(form.attachmentNames),
    content: form.content,
    custom_rules: parseJsonArray<ValidationEvalCustomRule>(
      form.customRules,
      "Custom rules",
    ),
    expected_issues: parseJsonArray<ValidationEvalExpectedIssue>(
      form.expectedIssues,
      "Expected issues",
    ),
    expected_context_questions: splitList(form.expectedContextQuestions),
    expected_questions: splitList(form.expectedQuestions),
    expected_verdict: form.expectedVerdict,
    external_id: form.externalId.trim(),
    historical_questions: splitList(form.historicalQuestions),
    metadata: parseJsonObject(form.metadata, "Metadata"),
    related_tasks: parseJsonArray<Record<string, unknown>>(
      form.relatedTasks,
      "Related tasks",
    ),
    tags: splitList(form.tags),
    title: form.title.trim(),
  };
}

function caseToForm(caseItem: ValidationEvalCaseRead): CaseFormState {
  return {
    attachmentNames: caseItem.attachment_names.join("\n"),
    content: caseItem.content,
    customRules: compactJson(caseItem.custom_rules),
    expectedContextQuestions: caseItem.expected_context_questions.join("\n"),
    expectedIssues: compactJson(caseItem.expected_issues),
    expectedQuestions: caseItem.expected_questions.join("\n"),
    expectedVerdict: caseItem.expected_verdict,
    externalId: caseItem.external_id,
    historicalQuestions: caseItem.historical_questions.join("\n"),
    metadata: compactJson(caseItem.metadata),
    relatedTasks: compactJson(caseItem.related_tasks),
    tags: caseItem.tags.join("\n"),
    title: caseItem.title,
  };
}

function isValidationPrompt(config: AgentPromptConfigRead) {
  return (
    config.agent_key === "task-validation" ||
    config.prompt_key.startsWith("task-validation") ||
    config.prompt_key === "validation-eval-question-judge"
  );
}

function makePromptVersionLabel(version: AgentPromptVersionRead) {
  return `v${version.revision} / ${formatDateTimeFull(version.created_at)}`;
}

function cloneDefaultConfig(): ValidationEvalRunConfig {
  return {
    judge_provider_config_ids: [...DEFAULT_CONFIG.judge_provider_config_ids],
    run_question_judge: DEFAULT_CONFIG.run_question_judge,
    variants: DEFAULT_CONFIG.variants.map((variant) => ({
      ...variant,
      prompt_version_ids: { ...variant.prompt_version_ids },
      validation_node_settings: { ...variant.validation_node_settings },
    })),
  };
}

export default function ValidationEvalPage() {
  const [activeTab, setActiveTab] = useState<ValidationEvalTab>("import");
  const [projects, setProjects] = useState<ProjectRead[]>([]);
  const [providers, setProviders] = useState<ProviderConfigRead[]>([]);
  const [promptConfigs, setPromptConfigs] = useState<AgentPromptConfigRead[]>(
    [],
  );
  const [promptVersionsByKey, setPromptVersionsByKey] = useState<
    Record<string, AgentPromptVersionRead[]>
  >({});
  const [datasets, setDatasets] = useState<ValidationEvalDatasetRead[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [datasetDetail, setDatasetDetail] =
    useState<ValidationEvalDatasetDetailRead | null>(null);
  const [activeRun, setActiveRun] = useState<ValidationEvalRunRead | null>(
    null,
  );
  const [runHistory, setRunHistory] =
    useState<ValidationEvalRunPageRead | null>(null);
  const [runHistoryPage, setRunHistoryPage] = useState(1);
  const [runHistoryStatus, setRunHistoryStatus] =
    useState<RunStatusFilter>("all");
  const [caseStatusFilter, setCaseStatusFilter] =
    useState<CaseStatusFilter>("all");
  const [caseVariantFilter, setCaseVariantFilter] = useState("all");
  const [caseSearch, setCaseSearch] = useState("");
  const [importFormat, setImportFormat] =
    useState<ValidationEvalImportFormat>("json");
  const [importContent, setImportContent] = useState(JSON_TEMPLATE);
  const [importDatasetName, setImportDatasetName] = useState("");
  const [caseForm, setCaseForm] = useState<CaseFormState>(EMPTY_CASE_FORM);
  const [editingCaseId, setEditingCaseId] = useState<string | null>(null);
  const [config, setConfig] =
    useState<ValidationEvalRunConfig>(cloneDefaultConfig);
  const [exportArtifact, setExportArtifact] =
    useState<ValidationEvalExportArtifact>("case_results");
  const [exportFormat, setExportFormat] = useState<ExportFormat>("csv");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [runHistoryLoading, setRunHistoryLoading] = useState(false);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [deletingDatasetId, setDeletingDatasetId] = useState<string | null>(
    null,
  );
  const [deletingCaseId, setDeletingCaseId] = useState<string | null>(null);
  const [runPendingDeletion, setRunPendingDeletion] =
    useState<ValidationEvalRunListItemRead | null>(null);
  const [datasetPendingDeletion, setDatasetPendingDeletion] =
    useState<ValidationEvalDatasetRead | null>(null);
  const [casePendingDeletion, setCasePendingDeletion] =
    useState<ValidationEvalCaseRead | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.id === selectedDatasetId) ?? null,
    [datasets, selectedDatasetId],
  );

  const validationPromptConfigs = useMemo(
    () => promptConfigs.filter(isValidationPrompt),
    [promptConfigs],
  );

  const selectedVariant = config.variants[0] ?? makeLevelVariant("core_rules");

  const caseVariantOptions = useMemo(() => {
    const keys = new Set<string>();
    activeRun?.case_results.forEach((item) => keys.add(item.variant_key));
    keys.add(selectedVariant.key);
    return Array.from(keys).sort();
  }, [activeRun?.case_results, selectedVariant.key]);

  const filteredCaseResults = useMemo(() => {
    const query = normalizedText(caseSearch);
    return (activeRun?.case_results ?? []).filter((item) => {
      if (caseStatusFilter !== "all" && item.status !== caseStatusFilter) {
        return false;
      }
      if (
        caseVariantFilter !== "all" &&
        item.variant_key !== caseVariantFilter
      ) {
        return false;
      }
      if (!query) {
        return true;
      }
      return normalizedText(
        `${item.case_external_id} ${item.variant_key} ${compactJson(
          item.actual_result,
        )} ${compactJson(item.diffs)}`,
      ).includes(query);
    });
  }, [
    activeRun?.case_results,
    caseSearch,
    caseStatusFilter,
    caseVariantFilter,
  ]);

  const judgeProviderSelectionError =
    config.run_question_judge && config.judge_provider_config_ids.length > 3
      ? "Выберите не больше 3 LLM-профилей или снимите все для runtime default."
      : null;

  async function loadBootstrap() {
    try {
      setLoading(true);
      setError(null);
      const [loadedProjects, loadedDatasets, loadedProviders, loadedPrompts] =
        await Promise.all([
          projectsApi.list(),
          adminApi.listValidationEvalDatasets(),
          adminApi.listProviders(),
          adminApi.listPromptConfigs(),
        ]);
      setProjects(loadedProjects);
      setDatasets(loadedDatasets);
      setProviders(loadedProviders.filter((provider) => provider.enabled));
      setPromptConfigs(loadedPrompts);

      const validationPrompts = loadedPrompts.filter(isValidationPrompt);
      const versionEntries = await Promise.all(
        validationPrompts.map(async (prompt) => {
          try {
            const versions = await adminApi.listPromptVersions(
              prompt.prompt_key,
            );
            return [prompt.prompt_key, versions] as const;
          } catch {
            return [prompt.prompt_key, []] as const;
          }
        }),
      );
      setPromptVersionsByKey(Object.fromEntries(versionEntries));

      const nextProjectId = loadedProjects[0]?.id ?? "";
      setSelectedProjectId(nextProjectId);
      const nextDatasetId = loadedDatasets[0]?.id ?? "";
      setSelectedDatasetId(nextDatasetId);
      if (nextDatasetId) {
        await loadDataset(nextDatasetId);
        await loadRunHistory(nextDatasetId, 1, "all");
      }
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить Validation Eval Lab."),
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadBootstrap();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selectedDatasetId) {
      setDatasetDetail(null);
      setRunHistory(null);
      return;
    }
    void loadDataset(selectedDatasetId);
    void loadRunHistory(selectedDatasetId, runHistoryPage, runHistoryStatus);
  }, [selectedDatasetId, runHistoryPage, runHistoryStatus]); // eslint-disable-line react-hooks/exhaustive-deps

  async function reloadDatasets(preferredDatasetId = selectedDatasetId) {
    const loadedDatasets = await adminApi.listValidationEvalDatasets();
    setDatasets(loadedDatasets);
    if (!preferredDatasetId && loadedDatasets[0]) {
      setSelectedDatasetId(loadedDatasets[0].id);
      return;
    }
    if (
      preferredDatasetId &&
      loadedDatasets.some((dataset) => dataset.id === preferredDatasetId)
    ) {
      setSelectedDatasetId(preferredDatasetId);
      return;
    }
    setSelectedDatasetId(loadedDatasets[0]?.id ?? "");
  }

  async function loadDataset(datasetId: string) {
    try {
      const detail = await adminApi.getValidationEvalDataset(datasetId);
      setDatasetDetail(detail);
    } catch (caught) {
      setDatasetDetail(null);
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить набор кейсов."),
      );
    }
  }

  async function loadRunHistory(
    datasetId = selectedDatasetId,
    page = runHistoryPage,
    status = runHistoryStatus,
  ) {
    if (!datasetId) {
      setRunHistory(null);
      return;
    }
    try {
      setRunHistoryLoading(true);
      const history = await adminApi.listValidationEvalRuns(datasetId, {
        page,
        size: RUN_HISTORY_PAGE_SIZE,
        ...(status === "all" ? {} : { status }),
      });
      setRunHistory(history);
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить историю запусков."),
      );
    } finally {
      setRunHistoryLoading(false);
    }
  }

  function updateSelectedVariant(
    updater: (
      variant: ValidationEvalVariantConfig,
    ) => ValidationEvalVariantConfig,
  ) {
    setConfig((current) => ({
      ...current,
      variants: [
        updater(current.variants[0] ?? makeLevelVariant("core_rules")),
      ],
    }));
  }

  async function handleImport(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setBusy(true);
      setError(null);
      setNotice(null);
      const result = await adminApi.importValidationEvalDataset({
        content: importContent,
        dataset_name: importDatasetName.trim() || null,
        format: importFormat,
        project_id: selectedProjectId || null,
      });
      await reloadDatasets(result.dataset.id);
      setDatasetDetail(result.dataset);
      setSelectedDatasetId(result.dataset.id);
      setActiveTab("datasets");
      setNotice(
        `Импортировано кейсов: ${result.imported_cases}. ${
          result.warnings.length ? `Warnings: ${result.warnings.length}` : ""
        }`.trim(),
      );
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось импортировать набор."));
    } finally {
      setBusy(false);
    }
  }

  async function handleCaseSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDatasetId) {
      setError("Выберите набор перед сохранением кейса.");
      return;
    }
    try {
      setBusy(true);
      setError(null);
      setNotice(null);
      const payload = buildCasePayload(caseForm);
      if (editingCaseId) {
        await adminApi.updateValidationEvalCase(
          selectedDatasetId,
          editingCaseId,
          payload,
        );
        setNotice("Кейс обновлен.");
      } else {
        await adminApi.createValidationEvalCase(selectedDatasetId, payload);
        setNotice("Кейс создан.");
      }
      setCaseForm(EMPTY_CASE_FORM);
      setEditingCaseId(null);
      await loadDataset(selectedDatasetId);
      await reloadDatasets(selectedDatasetId);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось сохранить кейс."));
    } finally {
      setBusy(false);
    }
  }

  async function handleRun(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDatasetId) {
      setError("Выберите набор перед запуском Validation Eval.");
      return;
    }
    if (judgeProviderSelectionError) {
      setError(judgeProviderSelectionError);
      return;
    }
    try {
      setBusy(true);
      setError(null);
      setNotice(null);
      const run = await adminApi.createValidationEvalRun(selectedDatasetId, {
        ...config,
        variants: [selectedVariant],
      });
      const runDetail = await adminApi.getValidationEvalRun(run.id);
      setActiveRun(runDetail);
      setActiveTab("results");
      await reloadDatasets(selectedDatasetId);
      await loadRunHistory(selectedDatasetId, runHistoryPage, runHistoryStatus);
      setNotice("Validation Eval run создан.");
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось запустить Validation Eval."),
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenRun(runId: string) {
    try {
      setBusy(true);
      setError(null);
      const runDetail = await adminApi.getValidationEvalRun(runId);
      setActiveRun(runDetail);
      setActiveTab("results");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось открыть запуск."));
    } finally {
      setBusy(false);
    }
  }

  async function handleExport(
    artifact = exportArtifact,
    format = exportFormat,
    runId = activeRun?.id,
  ) {
    if (!runId) {
      setError("Нет выбранного запуска для экспорта.");
      return;
    }
    try {
      setError(null);
      const content = await adminApi.exportValidationEvalRun(
        runId,
        artifact,
        format,
      );
      downloadText(
        `validation-eval-${artifact}-${runId}.${format}`,
        content,
        format === "json"
          ? "application/json;charset=utf-8"
          : "text/csv;charset=utf-8",
      );
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось выгрузить артефакт."));
    }
  }

  async function confirmRunDelete() {
    if (!runPendingDeletion) {
      return;
    }
    try {
      setDeletingRunId(runPendingDeletion.id);
      setError(null);
      await adminApi.deleteValidationEvalRun(runPendingDeletion.id);
      if (activeRun?.id === runPendingDeletion.id) {
        setActiveRun(null);
      }
      await reloadDatasets(selectedDatasetId);
      await loadRunHistory(selectedDatasetId, runHistoryPage, runHistoryStatus);
      setRunPendingDeletion(null);
      setNotice("Запуск удален.");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить запуск."));
    } finally {
      setDeletingRunId(null);
    }
  }

  async function confirmDatasetDelete() {
    if (!datasetPendingDeletion) {
      return;
    }
    try {
      setDeletingDatasetId(datasetPendingDeletion.id);
      setError(null);
      await adminApi.deleteValidationEvalDataset(datasetPendingDeletion.id);
      if (selectedDatasetId === datasetPendingDeletion.id) {
        setDatasetDetail(null);
        setActiveRun(null);
        setRunHistory(null);
      }
      await reloadDatasets("");
      setDatasetPendingDeletion(null);
      setNotice("Набор удален.");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить набор."));
    } finally {
      setDeletingDatasetId(null);
    }
  }

  async function confirmCaseDelete() {
    if (!casePendingDeletion || !selectedDatasetId) {
      return;
    }
    try {
      setDeletingCaseId(casePendingDeletion.id);
      setError(null);
      await adminApi.deleteValidationEvalCase(
        selectedDatasetId,
        casePendingDeletion.id,
      );
      await loadDataset(selectedDatasetId);
      await reloadDatasets(selectedDatasetId);
      if (editingCaseId === casePendingDeletion.id) {
        setEditingCaseId(null);
        setCaseForm(EMPTY_CASE_FORM);
      }
      setCasePendingDeletion(null);
      setNotice("Кейс удален.");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить кейс."));
    } finally {
      setDeletingCaseId(null);
    }
  }

  function renderImport() {
    return (
      <form className="page-panel space-y-5 p-5" onSubmit={handleImport}>
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-[#44546f]">
              Проект
            </span>
            <select
              className="ui-field"
              onChange={(event) => setSelectedProjectId(event.target.value)}
              value={selectedProjectId}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-[#44546f]">
              Dataset name override
            </span>
            <input
              className="ui-field"
              onChange={(event) => setImportDatasetName(event.target.value)}
              placeholder="Оставьте пустым, если имя есть в файле"
              value={importDatasetName}
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-[#44546f]">
              Формат
            </span>
            <select
              className="ui-field min-w-36"
              onChange={(event) => {
                const nextFormat = event.target
                  .value as ValidationEvalImportFormat;
                setImportFormat(nextFormat);
                setImportContent(
                  nextFormat === "json" ? JSON_TEMPLATE : CSV_TEMPLATE,
                );
              }}
              value={importFormat}
            >
              <option value="json">JSON</option>
              <option value="csv">CSV</option>
            </select>
          </label>
        </div>

        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-[#44546f]">
            Содержимое датасета
          </span>
          <textarea
            className="ui-field min-h-[420px] resize-y font-mono text-xs leading-6"
            onChange={(event) => setImportContent(event.target.value)}
            spellCheck={false}
            value={importContent}
          />
        </label>

        <div className="flex flex-wrap gap-3">
          <button className="ui-button-primary" disabled={busy} type="submit">
            {busy ? "Импортируем..." : "Импортировать набор"}
          </button>
          <button
            className="ui-button-secondary"
            onClick={() =>
              setImportContent(
                importFormat === "json" ? JSON_TEMPLATE : CSV_TEMPLATE,
              )
            }
            type="button"
          >
            Вернуть шаблон
          </button>
        </div>
      </form>
    );
  }

  function renderDatasets() {
    return (
      <section className="page-panel overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-[rgba(9,30,66,0.1)] p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="section-eyebrow">Datasets</p>
            <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
              Наборы Validation Eval
            </h3>
          </div>
          <button
            className="ui-button-secondary"
            onClick={() => void reloadDatasets(selectedDatasetId)}
            type="button"
          >
            Обновить
          </button>
        </div>

        {datasets.length === 0 ? (
          <p className="p-5 text-sm text-[#626f86]">
            Пока нет наборов. Импортируйте JSON или CSV на вкладке импорта.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[780px] text-left text-sm">
              <thead className="bg-[#fafbfc] text-xs uppercase tracking-[0.12em] text-[#626f86]">
                <tr>
                  <th className="px-4 py-3">Dataset</th>
                  <th className="px-4 py-3">Проект</th>
                  <th className="px-4 py-3">Cases</th>
                  <th className="px-4 py-3">Last run</th>
                  <th className="px-4 py-3">Updated</th>
                  <th className="px-4 py-3 text-right">Действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                {datasets.map((dataset) => {
                  const isActive = dataset.id === selectedDatasetId;
                  return (
                    <tr
                      className={isActive ? "bg-[#f4f8ff]" : "bg-white"}
                      key={dataset.id}
                    >
                      <td className="px-4 py-4">
                        <p className="font-semibold text-[#172b4d]">
                          {dataset.name}
                        </p>
                        <p className="mt-1 text-xs text-[#626f86]">
                          {dataset.id}
                        </p>
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {dataset.project_name ?? dataset.project_id}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {dataset.cases_total}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {statusLabel(dataset.last_run_status)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {formatDateTimeFull(dataset.updated_at)}
                      </td>
                      <td className="px-4 py-4">
                        <div className="flex justify-end gap-2">
                          <button
                            className={
                              isActive
                                ? "ui-button-primary"
                                : "ui-button-secondary"
                            }
                            onClick={() => {
                              setSelectedDatasetId(dataset.id);
                              setActiveTab("cases");
                            }}
                            type="button"
                          >
                            Открыть
                          </button>
                          <button
                            className="ui-button-danger"
                            onClick={() => setDatasetPendingDeletion(dataset)}
                            type="button"
                          >
                            Удалить
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    );
  }

  function renderCases() {
    return (
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(360px,440px)]">
        <section className="page-panel overflow-hidden">
          <div className="border-b border-[rgba(9,30,66,0.1)] p-5">
            <p className="section-eyebrow">Cases</p>
            <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
              {selectedDataset?.name ?? "Набор не выбран"}
            </h3>
            <p className="mt-2 text-sm text-[#626f86]">
              Кейсы не создают задачи и используются только для eval-запусков.
            </p>
          </div>

          {!datasetDetail ? (
            <p className="p-5 text-sm text-[#626f86]">Выберите набор.</p>
          ) : datasetDetail.cases.length === 0 ? (
            <p className="p-5 text-sm text-[#626f86]">
              В наборе пока нет кейсов.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] text-left text-sm">
                <thead className="bg-[#fafbfc] text-xs uppercase tracking-[0.12em] text-[#626f86]">
                  <tr>
                    <th className="px-4 py-3">Case</th>
                    <th className="px-4 py-3">Verdict</th>
                    <th className="px-4 py-3">Issues</th>
                    <th className="px-4 py-3">Questions</th>
                    <th className="px-4 py-3">Context Q</th>
                    <th className="px-4 py-3">Tags</th>
                    <th className="px-4 py-3 text-right">Действия</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                  {datasetDetail.cases.map((caseItem) => (
                    <tr key={caseItem.id}>
                      <td className="px-4 py-4">
                        <p className="font-semibold text-[#172b4d]">
                          {caseItem.external_id}
                        </p>
                        <p className="mt-1 text-[#44546f]">{caseItem.title}</p>
                        <p className="mt-1 max-w-xl text-xs text-[#626f86]">
                          {shortText(caseItem.content)}
                        </p>
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {getValidationVerdictLabel(caseItem.expected_verdict)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {caseItem.expected_issues.length}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {caseItem.expected_questions.length}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {caseItem.expected_context_questions.length}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {caseItem.tags.join(", ") || "н/д"}
                      </td>
                      <td className="px-4 py-4">
                        <div className="flex justify-end gap-2">
                          <button
                            className="ui-button-secondary"
                            onClick={() => {
                              setEditingCaseId(caseItem.id);
                              setCaseForm(caseToForm(caseItem));
                            }}
                            type="button"
                          >
                            Редактировать
                          </button>
                          <button
                            className="ui-button-danger"
                            onClick={() => setCasePendingDeletion(caseItem)}
                            type="button"
                          >
                            Удалить
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <form className="page-panel space-y-4 p-5" onSubmit={handleCaseSubmit}>
          <div>
            <p className="section-eyebrow">Manual case</p>
            <h3 className="mt-2 text-lg font-semibold text-[#172b4d]">
              {editingCaseId ? "Редактирование кейса" : "Новый кейс"}
            </h3>
          </div>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-[#44546f]">
              External ID
            </span>
            <input
              className="ui-field"
              onChange={(event) =>
                setCaseForm((current) => ({
                  ...current,
                  externalId: event.target.value,
                }))
              }
              required
              value={caseForm.externalId}
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-[#44546f]">
              Название
            </span>
            <input
              className="ui-field"
              onChange={(event) =>
                setCaseForm((current) => ({
                  ...current,
                  title: event.target.value,
                }))
              }
              required
              value={caseForm.title}
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-[#44546f]">
              Текст задачи
            </span>
            <textarea
              className="ui-field min-h-32 resize-y"
              onChange={(event) =>
                setCaseForm((current) => ({
                  ...current,
                  content: event.target.value,
                }))
              }
              value={caseForm.content}
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                Verdict
              </span>
              <select
                className="ui-field"
                onChange={(event) =>
                  setCaseForm((current) => ({
                    ...current,
                    expectedVerdict: event.target
                      .value as ValidationEvalVerdict,
                  }))
                }
                value={caseForm.expectedVerdict}
              >
                <option value="approved">approved</option>
                <option value="needs_rework">needs_rework</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                Tags
              </span>
              <textarea
                className="ui-field min-h-24 resize-y"
                onChange={(event) =>
                  setCaseForm((current) => ({
                    ...current,
                    tags: event.target.value,
                  }))
                }
                placeholder="auth&#10;security"
                value={caseForm.tags}
              />
            </label>
          </div>

          {[
            ["attachmentNames", "Вложения", "auth.md"],
            [
              "historicalQuestions",
              "Исторические вопросы",
              "Какие роли нужны?",
            ],
            [
              "expectedQuestions",
              "Ожидаемые вопросы",
              "Какие роли пользователей?",
            ],
            [
              "expectedContextQuestions",
              "Expected context questions",
              "Какие ограничения из прошлых задач нужно учесть?",
            ],
          ].map(([key, label, placeholder]) => (
            <label className="block" key={key}>
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                {label}
              </span>
              <textarea
                className="ui-field min-h-24 resize-y"
                onChange={(event) =>
                  setCaseForm((current) => ({
                    ...current,
                    [key]: event.target.value,
                  }))
                }
                placeholder={placeholder}
                value={caseForm[key as keyof CaseFormState]}
              />
            </label>
          ))}

          {[
            ["customRules", "Custom rules JSON"],
            ["relatedTasks", "Related tasks JSON"],
            ["expectedIssues", "Expected issues JSON"],
            ["metadata", "Metadata JSON"],
          ].map(([key, label]) => (
            <label className="block" key={key}>
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                {label}
              </span>
              <textarea
                className="ui-field min-h-28 resize-y font-mono text-xs leading-5"
                onChange={(event) =>
                  setCaseForm((current) => ({
                    ...current,
                    [key]: event.target.value,
                  }))
                }
                spellCheck={false}
                value={caseForm[key as keyof CaseFormState]}
              />
            </label>
          ))}

          <div className="flex flex-wrap gap-3">
            <button
              className="ui-button-primary"
              disabled={busy || !selectedDatasetId}
              type="submit"
            >
              {editingCaseId ? "Сохранить кейс" : "Создать кейс"}
            </button>
            {editingCaseId ? (
              <button
                className="ui-button-secondary"
                onClick={() => {
                  setEditingCaseId(null);
                  setCaseForm(EMPTY_CASE_FORM);
                }}
                type="button"
              >
                Отменить
              </button>
            ) : null}
          </div>
        </form>
      </div>
    );
  }

  function renderRun() {
    return (
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(360px,420px)]">
        <form className="page-panel space-y-5 p-5" onSubmit={handleRun}>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="section-eyebrow">Run config</p>
              <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
                Уровень проверки
              </h3>
              <p className="mt-2 text-sm text-[#626f86]">
                Один run считает метрики только для выбранного уровня.
              </p>
            </div>
            <button
              className="ui-button-secondary"
              onClick={() => setConfig(cloneDefaultConfig())}
              type="button"
            >
              Сбросить
            </button>
          </div>

          <label className="flex items-center gap-3 rounded-[10px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] px-4 py-3 text-sm text-[#172b4d]">
            <input
              checked={config.run_question_judge}
              onChange={(event) =>
                setConfig((current) => ({
                  ...current,
                  run_question_judge: event.target.checked,
                  judge_provider_config_ids: event.target.checked
                    ? current.judge_provider_config_ids
                    : [],
                }))
              }
              type="checkbox"
            />
            Запускать LangGraph judge для качества вопросов
          </label>

          {config.run_question_judge ? (
            <div className="rounded-[10px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] p-4">
              <p className="text-sm font-semibold text-[#172b4d]">
                Judge providers
              </p>
              <p className="mt-1 text-sm text-[#626f86]">
                0 профилей — runtime default. Для явного сравнения выберите от 1
                до 3.
              </p>
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                {providers.map((provider) => {
                  const checked = config.judge_provider_config_ids.includes(
                    provider.id,
                  );
                  const disabled =
                    !checked && config.judge_provider_config_ids.length >= 3;
                  return (
                    <label
                      className="flex items-center gap-3 rounded-[10px] border border-[rgba(9,30,66,0.1)] bg-white px-3 py-2 text-sm text-[#172b4d]"
                      key={provider.id}
                    >
                      <input
                        checked={checked}
                        disabled={disabled}
                        onChange={(event) =>
                          setConfig((current) => ({
                            ...current,
                            judge_provider_config_ids: event.target.checked
                              ? [
                                  ...current.judge_provider_config_ids,
                                  provider.id,
                                ]
                              : current.judge_provider_config_ids.filter(
                                  (id) => id !== provider.id,
                                ),
                          }))
                        }
                        type="checkbox"
                      />
                      <span>
                        {provider.name} /{" "}
                        {getProviderKindLabel(provider.provider_kind)} /{" "}
                        {provider.model}
                      </span>
                    </label>
                  );
                })}
              </div>
              {judgeProviderSelectionError ? (
                <p className="mt-3 text-sm font-semibold text-[#ae2e24]">
                  {judgeProviderSelectionError}
                </p>
              ) : null}
            </div>
          ) : null}

          <fieldset className="grid gap-3 md:grid-cols-3">
            <legend className="sr-only">Уровень Validation Eval</legend>
            {VALIDATION_LEVEL_VARIANTS.map((level) => (
              <label
                className="flex min-h-[132px] cursor-pointer flex-col gap-3 rounded-[10px] border border-[rgba(9,30,66,0.12)] bg-white p-4 text-sm text-[#172b4d]"
                key={level.key}
              >
                <span className="flex items-center gap-3 font-semibold">
                  <input
                    checked={selectedVariant.key === level.key}
                    name="validation-eval-level"
                    onChange={() =>
                      setConfig((current) => ({
                        ...current,
                        variants: [
                          makeLevelVariant(level.key, current.variants[0]),
                        ],
                      }))
                    }
                    type="radio"
                  />
                  {level.label}
                </span>
                <span className="text-[#626f86]">{level.description}</span>
              </label>
            ))}
          </fieldset>

          <div className="grid gap-4 lg:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                Provider override
              </span>
              <select
                className="ui-field"
                onChange={(event) =>
                  updateSelectedVariant((current) => ({
                    ...current,
                    provider_config_id: event.target.value || null,
                  }))
                }
                value={selectedVariant.provider_config_id ?? ""}
              >
                <option value="">Runtime default</option>
                {providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name} /{" "}
                    {getProviderKindLabel(provider.provider_kind)} /{" "}
                    {provider.model}
                  </option>
                ))}
              </select>
            </label>
            <div className="rounded-[10px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] p-3">
              <p className="text-sm font-semibold text-[#44546f]">
                Prompt version overrides
              </p>
              <div className="mt-3 space-y-3">
                {validationPromptConfigs.length === 0 ? (
                  <p className="text-sm text-[#626f86]">
                    Validation-промпты не найдены.
                  </p>
                ) : (
                  validationPromptConfigs.map((prompt) => (
                    <label className="block" key={prompt.prompt_key}>
                      <span className="mb-1 block text-xs font-semibold text-[#626f86]">
                        {prompt.prompt_key}
                      </span>
                      <select
                        className="ui-field py-2 text-xs"
                        onChange={(event) =>
                          updateSelectedVariant((current) => {
                            const promptVersionIds = {
                              ...current.prompt_version_ids,
                            };
                            if (event.target.value) {
                              promptVersionIds[prompt.prompt_key] =
                                event.target.value;
                            } else {
                              delete promptVersionIds[prompt.prompt_key];
                            }
                            return {
                              ...current,
                              prompt_version_ids: promptVersionIds,
                            };
                          })
                        }
                        value={
                          selectedVariant.prompt_version_ids[
                            prompt.prompt_key
                          ] ?? ""
                        }
                      >
                        <option value="">Effective prompt</option>
                        {(promptVersionsByKey[prompt.prompt_key] ?? []).map(
                          (version) => (
                            <option key={version.id} value={version.id}>
                              {makePromptVersionLabel(version)}
                            </option>
                          ),
                        )}
                      </select>
                    </label>
                  ))
                )}
              </div>
            </div>
          </div>

          <button
            className="ui-button-primary"
            disabled={
              busy || !selectedDatasetId || Boolean(judgeProviderSelectionError)
            }
            type="submit"
          >
            {busy ? "Запускаем..." : "Запустить Validation Eval"}
          </button>
        </form>

        <section className="page-panel overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-[rgba(9,30,66,0.1)] p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="section-eyebrow">Run history</p>
              <h3 className="mt-2 text-lg font-semibold text-[#172b4d]">
                История запусков
              </h3>
            </div>
            <select
              aria-label="Run status"
              className="ui-field max-w-52"
              onChange={(event) => {
                setRunHistoryStatus(event.target.value as RunStatusFilter);
                setRunHistoryPage(1);
              }}
              value={runHistoryStatus}
            >
              {RUN_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {runHistoryLoading ? (
            <div className="p-5">
              <LoadingSpinner label="Загружаем историю" />
            </div>
          ) : !runHistory || runHistory.items.length === 0 ? (
            <p className="p-5 text-sm text-[#626f86]">
              Запусков для выбранного набора пока нет.
            </p>
          ) : (
            <div className="divide-y divide-[rgba(9,30,66,0.08)]">
              {runHistory.items.map((run) => {
                const metrics = asRecord(run.summary_metrics);
                const variants = asRecord(metrics.variants);
                return (
                  <article className="p-5" key={run.id}>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="font-semibold text-[#172b4d]">
                          {formatDateTimeFull(run.created_at)}
                        </p>
                        <p className="mt-1 text-sm text-[#626f86]">
                          {statusLabel(run.status)} / уровни:{" "}
                          {Object.keys(variants).join(", ") || "н/д"}
                        </p>
                        <p className="mt-1 text-xs text-[#626f86]">
                          {run.error_message ?? run.id}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2 sm:justify-end">
                        <button
                          className="ui-button-secondary"
                          onClick={() => void handleOpenRun(run.id)}
                          type="button"
                        >
                          Открыть
                        </button>
                        <button
                          className="ui-button-secondary"
                          onClick={() =>
                            void handleExport("case_results", "csv", run.id)
                          }
                          type="button"
                        >
                          CSV
                        </button>
                        <button
                          className="ui-button-danger"
                          onClick={() => setRunPendingDeletion(run)}
                          type="button"
                        >
                          Удалить
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {runHistory && runHistory.total > RUN_HISTORY_PAGE_SIZE ? (
            <div className="flex justify-end gap-2 border-t border-[rgba(9,30,66,0.08)] p-4">
              <button
                className="ui-button-secondary"
                disabled={runHistoryPage <= 1}
                onClick={() =>
                  setRunHistoryPage((page) => Math.max(1, page - 1))
                }
                type="button"
              >
                Назад
              </button>
              <button
                className="ui-button-secondary"
                disabled={
                  runHistoryPage * RUN_HISTORY_PAGE_SIZE >= runHistory.total
                }
                onClick={() => setRunHistoryPage((page) => page + 1)}
                type="button"
              >
                Вперед
              </button>
            </div>
          ) : null}
        </section>
      </div>
    );
  }

  function renderResults() {
    if (!activeRun) {
      return (
        <p className="page-panel p-5 text-sm text-[#626f86]">
          Откройте запуск из истории или создайте новый run.
        </p>
      );
    }

    const summary = asRecord(activeRun.summary_metrics);
    const variants = asRecord(summary.variants);

    return (
      <div className="space-y-6">
        <section className="page-panel p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="section-eyebrow">Run status</p>
              <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
                {statusLabel(activeRun.status)}
              </h3>
              <p className="mt-2 text-sm text-[#626f86]">
                {activeRun.dataset_name ?? activeRun.dataset_id} /{" "}
                {formatDateTimeFull(activeRun.created_at)}
              </p>
              {activeRun.error_message ? (
                <p className="mt-2 text-sm font-semibold text-[#ae2e24]">
                  {activeRun.error_message}
                </p>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                aria-label="Export artifact"
                className="ui-field max-w-56"
                onChange={(event) =>
                  setExportArtifact(
                    event.target.value as ValidationEvalExportArtifact,
                  )
                }
                value={exportArtifact}
              >
                {EXPORT_ARTIFACTS.map((artifact) => (
                  <option key={artifact.value} value={artifact.value}>
                    {artifact.label}
                  </option>
                ))}
              </select>
              <select
                aria-label="Export format"
                className="ui-field max-w-32"
                onChange={(event) =>
                  setExportFormat(event.target.value as ExportFormat)
                }
                value={exportFormat}
              >
                <option value="csv">CSV</option>
                <option value="json">JSON</option>
              </select>
              <button
                className="ui-button-secondary"
                onClick={() => void handleExport()}
                type="button"
              >
                Export
              </button>
            </div>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile label="Total results" value={summary.total_results} />
          <MetricTile label="Latency" value={formatMs(activeRun.latency_ms)} />
          <MetricTile
            label="Started"
            value={
              activeRun.started_at
                ? formatDateTimeFull(activeRun.started_at)
                : "н/д"
            }
          />
          <MetricTile
            label="Finished"
            value={
              activeRun.finished_at
                ? formatDateTimeFull(activeRun.finished_at)
                : "н/д"
            }
          />
        </section>

        <section className="page-panel overflow-hidden">
          <div className="border-b border-[rgba(9,30,66,0.1)] p-5">
            <p className="section-eyebrow">Metrics</p>
            <h3 className="mt-2 text-lg font-semibold text-[#172b4d]">
              Метрики выбранного уровня
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-left text-sm">
              <thead className="bg-[#fafbfc] text-xs uppercase tracking-[0.12em] text-[#626f86]">
                <tr>
                  <th className="px-4 py-3">Уровень</th>
                  <th className="px-4 py-3">Pass</th>
                  <th className="px-4 py-3">Verdict accuracy</th>
                  <th className="px-4 py-3">Issue F1</th>
                  <th className="px-4 py-3">Severity</th>
                  <th className="px-4 py-3">Custom rules</th>
                  <th className="px-4 py-3">Question F1</th>
                  <th className="px-4 py-3">Context Q F1</th>
                  <th className="px-4 py-3">Overall Q F1</th>
                  <th className="px-4 py-3">Judge</th>
                  <th className="px-4 py-3">p95</th>
                  <th className="px-4 py-3">Tokens</th>
                  <th className="px-4 py-3">Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                {Object.entries(variants).map(([variantKey, value]) => {
                  const metrics = asRecord(value);
                  const judge = asRecord(metrics.question_judge);
                  const contextJudge = asRecord(metrics.context_question_judge);
                  return (
                    <tr key={variantKey}>
                      <td className="px-4 py-4 font-semibold text-[#172b4d]">
                        {variantKey}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {metricValue(metrics.pass_rate)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {metricValue(metrics.verdict_accuracy)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {metricValue(metrics.issue_f1)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {metricValue(metrics.severity_accuracy)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {metricValue(metrics.custom_rule_coverage)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {metricValue(metrics.question_f1)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {metricValue(metrics.context_question_f1)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {metricValue(metrics.overall_question_f1)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        rel {metricValue(judge.relevance)} / spec{" "}
                        {metricValue(judge.specificity)}
                        <br />
                        ctx rel {metricValue(contextJudge.relevance)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {formatMs(metrics.p95_latency_ms as number | null)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {metricValue(metrics.total_tokens)}
                      </td>
                      <td className="px-4 py-4 text-[#44546f]">
                        {metricValue(metrics.estimated_cost_usd)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <div className="grid gap-6">
          <section className="page-panel overflow-hidden">
            <div className="border-b border-[rgba(9,30,66,0.1)] p-5">
              <p className="section-eyebrow">Confusion matrix</p>
              <h3 className="mt-2 text-lg font-semibold text-[#172b4d]">
                Approved / needs_rework
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-left text-sm">
                <thead className="bg-[#fafbfc] text-xs uppercase tracking-[0.12em] text-[#626f86]">
                  <tr>
                    <th className="px-4 py-3">Уровень</th>
                    <th className="px-4 py-3">Expected</th>
                    <th className="px-4 py-3">Actual</th>
                    <th className="px-4 py-3">Count</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                  {Object.entries(variants).flatMap(([variantKey, value]) => {
                    const matrix = asRecord(asRecord(value).confusion_matrix);
                    return Object.entries(matrix).flatMap(
                      ([expected, actuals]) =>
                        Object.entries(asRecord(actuals)).map(
                          ([actual, count]) => (
                            <tr key={`${variantKey}-${expected}-${actual}`}>
                              <td className="px-4 py-4 font-semibold text-[#172b4d]">
                                {variantKey}
                              </td>
                              <td className="px-4 py-4 text-[#44546f]">
                                {expected}
                              </td>
                              <td className="px-4 py-4 text-[#44546f]">
                                {actual}
                              </td>
                              <td className="px-4 py-4 text-[#44546f]">
                                {metricValue(count)}
                              </td>
                            </tr>
                          ),
                        ),
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <section className="page-panel p-5">
          <div className="grid gap-3 lg:grid-cols-[1fr_180px_180px]">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                Поиск
              </span>
              <input
                className="ui-field"
                onChange={(event) => setCaseSearch(event.target.value)}
                placeholder="case id, issue, question"
                value={caseSearch}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                Уровень
              </span>
              <select
                className="ui-field"
                onChange={(event) => setCaseVariantFilter(event.target.value)}
                value={caseVariantFilter}
              >
                <option value="all">Все уровни</option>
                {caseVariantOptions.map((variantKey) => (
                  <option key={variantKey} value={variantKey}>
                    {variantKey}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                Status
              </span>
              <select
                aria-label="Status"
                className="ui-field"
                onChange={(event) =>
                  setCaseStatusFilter(event.target.value as CaseStatusFilter)
                }
                value={caseStatusFilter}
              >
                {CASE_STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        <div className="space-y-4">
          {filteredCaseResults.length === 0 ? (
            <p className="page-panel p-5 text-sm text-[#626f86]">
              По текущим фильтрам результатов нет.
            </p>
          ) : (
            filteredCaseResults.map((item) => (
              <CaseResultCard item={item} key={item.id} />
            ))
          )}
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <section className="page-panel p-6">
        <LoadingSpinner label="Загружаем Validation Eval Lab" />
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <header className="page-panel p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="section-eyebrow">Validation Eval Lab</p>
            <h2 className="mt-3 text-3xl font-semibold text-[#172b4d]">
              Эксперименты валидатора
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-[#44546f]">
              Воспроизводимая среда для сравнения LangGraph-валидации по уровням
              правил, prompt versions и модельным профилям.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link className="ui-button-secondary" to="/admin/graph-runs">
              Графы
            </Link>
          </div>
        </div>

        <nav className="mt-6 flex flex-wrap gap-2" aria-label="Validation Eval">
          {TABS.map((tab) => (
            <button
              className={
                activeTab === tab.key
                  ? "ui-button-primary"
                  : "ui-button-secondary"
              }
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>

      {error ? (
        <div className="rounded-[12px] border border-[rgba(174,46,36,0.18)] bg-[#fdecec] px-4 py-3 text-sm font-semibold text-[#ae2e24]">
          {error}
        </div>
      ) : null}

      {notice ? (
        <div className="rounded-[12px] border border-[rgba(34,197,94,0.2)] bg-[#e8f5e9] px-4 py-3 text-sm font-semibold text-[#216e4e]">
          {notice}
        </div>
      ) : null}

      {activeTab === "import" ? renderImport() : null}
      {activeTab === "datasets" ? renderDatasets() : null}
      {activeTab === "cases" ? renderCases() : null}
      {activeTab === "run" ? renderRun() : null}
      {activeTab === "results" ? renderResults() : null}

      <ConfirmDialog
        busy={deletingRunId === runPendingDeletion?.id}
        confirmLabel="Удалить"
        description="Запуск и его результаты будут удалены. Активные queued/running запуски backend может запретить удалить."
        destructive
        onClose={() => setRunPendingDeletion(null)}
        onConfirm={confirmRunDelete}
        open={Boolean(runPendingDeletion)}
        title="Удалить запуск?"
      />
      <ConfirmDialog
        busy={deletingDatasetId === datasetPendingDeletion?.id}
        confirmLabel="Удалить"
        description="Набор, кейсы и завершенные результаты будут удалены. Активные queued/running запуски backend может запретить удалить."
        destructive
        onClose={() => setDatasetPendingDeletion(null)}
        onConfirm={confirmDatasetDelete}
        open={Boolean(datasetPendingDeletion)}
        title="Удалить набор?"
      />
      <ConfirmDialog
        busy={deletingCaseId === casePendingDeletion?.id}
        confirmLabel="Удалить"
        description="Кейс будет удален из выбранного eval-набора."
        destructive
        onClose={() => setCasePendingDeletion(null)}
        onConfirm={confirmCaseDelete}
        open={Boolean(casePendingDeletion)}
        title="Удалить кейс?"
      />
    </section>
  );
}

function MetricTile({ label, value }: { label: string; value: unknown }) {
  return (
    <article className="metric-tile">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#626f86]">
        {label}
      </p>
      <p className="mt-2 text-xl font-semibold text-[#172b4d]">
        {metricValue(value)}
      </p>
    </article>
  );
}

function CaseResultCard({ item }: { item: ValidationEvalCaseResultRead }) {
  const expectedIssues = asArray(item.expected_result.issues);
  const actualIssues = asArray(item.actual_result.issues);
  const expectedQuestions = asArray(item.expected_result.questions);
  const actualQuestions = asArray(item.actual_result.questions);
  const expectedContextQuestions = asArray(
    item.expected_result.context_questions,
  );
  const actualContextQuestions = asArray(item.actual_result.context_questions);
  const diffs = item.diffs;
  const judge = asRecord(item.judge_payload);
  const judgeScores = asRecord(item.metrics.question_judge);
  const finalQuestionJudgeRuns = judgeRunsFromGroup(judge.final_questions);
  const contextQuestionJudgeRuns = judgeRunsFromGroup(judge.context_questions);
  const judgeComparisonGroups: Array<[string, Array<Record<string, unknown>>]> =
    [
      ["final", finalQuestionJudgeRuns],
      ["context", contextQuestionJudgeRuns],
    ];

  return (
    <article className="page-panel p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="section-eyebrow">{item.variant_key}</p>
          <h3 className="mt-2 text-lg font-semibold text-[#172b4d]">
            {item.case_external_id}
          </h3>
          <p className="mt-2 text-sm text-[#626f86]">
            {statusLabel(item.status)} / {formatMs(item.latency_ms)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill status={item.status} />
          {item.graph_run_id ? (
            <Link className="ui-button-secondary" to="/admin/graph-runs">
              Graph {item.graph_run_id.slice(0, 8)}
            </Link>
          ) : null}
          {item.judge_graph_run_id ? (
            <Link className="ui-button-secondary" to="/admin/graph-runs">
              Judge {item.judge_graph_run_id.slice(0, 8)}
            </Link>
          ) : null}
        </div>
      </div>

      {item.error_message ? (
        <p className="mt-4 rounded-[10px] border border-[rgba(174,46,36,0.18)] bg-[#fdecec] px-4 py-3 text-sm font-semibold text-[#ae2e24]">
          {item.error_message}
        </p>
      ) : null}

      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-[#fafbfc] text-xs uppercase tracking-[0.12em] text-[#626f86]">
            <tr>
              <th className="px-4 py-3">Field</th>
              <th className="px-4 py-3">Expected</th>
              <th className="px-4 py-3">Actual</th>
              <th className="px-4 py-3">Metric</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
            <tr>
              <td className="px-4 py-3 font-semibold text-[#172b4d]">
                Verdict
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                {metricValue(item.expected_result.verdict)}
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                {metricValue(item.actual_result.verdict)}
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                {metricValue(item.metrics.verdict_match)}
              </td>
            </tr>
            <tr>
              <td className="px-4 py-3 font-semibold text-[#172b4d]">Issues</td>
              <td className="px-4 py-3 text-[#44546f]">
                {expectedIssues.length}
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                {actualIssues.length}
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                P {metricValue(item.metrics.issue_precision)} / R{" "}
                {metricValue(item.metrics.issue_recall)} / F1{" "}
                {metricValue(item.metrics.issue_f1)}
              </td>
            </tr>
            <tr>
              <td className="px-4 py-3 font-semibold text-[#172b4d]">
                Questions
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                {expectedQuestions.length}
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                {actualQuestions.length}
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                F1 {metricValue(item.metrics.question_f1)} / дубли{" "}
                {metricValue(item.metrics.question_duplicates)}
              </td>
            </tr>
            <tr>
              <td className="px-4 py-3 font-semibold text-[#172b4d]">
                Context questions
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                {expectedContextQuestions.length}
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                {actualContextQuestions.length}
              </td>
              <td className="px-4 py-3 text-[#44546f]">
                F1 {metricValue(item.metrics.context_question_f1)} / overall{" "}
                {metricValue(item.metrics.overall_question_f1)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <DiffList
          label="False positives"
          values={asArray(diffs.false_positive_issues)}
        />
        <DiffList
          label="False negatives"
          values={asArray(diffs.false_negative_issues)}
        />
        <DiffList
          label="Extra questions"
          values={asArray(diffs.extra_questions)}
        />
        <DiffList
          label="Missing questions"
          values={asArray(diffs.missing_questions)}
        />
        <DiffList
          label="Extra context questions"
          values={asArray(diffs.extra_context_questions)}
        />
        <DiffList
          label="Missing context questions"
          values={asArray(diffs.missing_context_questions)}
        />
      </div>

      {finalQuestionJudgeRuns.length || contextQuestionJudgeRuns.length ? (
        <div className="mt-5 overflow-x-auto rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-4">
          <h4 className="text-sm font-semibold text-[#172b4d]">
            Judge comparison
          </h4>
          <table className="mt-3 w-full min-w-[760px] text-left text-xs">
            <thead className="text-[#626f86]">
              <tr>
                <th className="py-2">Group</th>
                <th className="py-2">Provider</th>
                <th className="py-2">Rel</th>
                <th className="py-2">Spec</th>
                <th className="py-2">Action</th>
                <th className="py-2">Novelty</th>
                <th className="py-2">Rationale</th>
              </tr>
            </thead>
            <tbody>
              {judgeComparisonGroups.flatMap(([group, runs]) =>
                runs.map((run) => {
                  const payload = asRecord(run.payload);
                  return (
                    <tr key={`${group}-${String(run.index)}`}>
                      <td className="py-2 pr-3 font-semibold text-[#172b4d]">
                        {group}
                      </td>
                      <td className="py-2 pr-3 text-[#44546f]">
                        {metricValue(run.provider_kind)} /{" "}
                        {metricValue(run.model)}
                      </td>
                      <td className="py-2 pr-3">
                        {metricValue(payload.relevance)}
                      </td>
                      <td className="py-2 pr-3">
                        {metricValue(payload.specificity)}
                      </td>
                      <td className="py-2 pr-3">
                        {metricValue(payload.actionability)}
                      </td>
                      <td className="py-2 pr-3">
                        {metricValue(payload.novelty)}
                      </td>
                      <td className="py-2">
                        {shortText(payload.rationale, 140)}
                      </td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <JsonDetails label="Expected result" value={item.expected_result} />
        <JsonDetails label="Actual result" value={item.actual_result} />
        <JsonDetails label="Diffs" value={item.diffs} />
        <JsonDetails
          label="Judge result"
          value={
            Object.keys(judge).length
              ? judge
              : {
                  actionability: item.metrics.question_actionability,
                  novelty: item.metrics.question_novelty,
                  relevance:
                    judgeScores.relevance ?? item.metrics.question_relevance,
                  specificity:
                    judgeScores.specificity ??
                    item.metrics.question_specificity,
                }
          }
        />
      </div>
    </article>
  );
}

function StatusPill({ status }: { status: string }) {
  const statusClass =
    status === "passed"
      ? "border-[rgba(34,197,94,0.24)] bg-[#e8f5e9] text-[#216e4e]"
      : status === "failed"
        ? "border-[rgba(255,171,0,0.28)] bg-[#fff4e5] text-[#974f0c]"
        : "border-[rgba(174,46,36,0.18)] bg-[#fdecec] text-[#ae2e24]";
  return (
    <span className={`status-pill ${statusClass}`}>{statusLabel(status)}</span>
  );
}

function DiffList({ label, values }: { label: string; values: unknown[] }) {
  return (
    <div className="rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-4">
      <h4 className="text-sm font-semibold text-[#172b4d]">
        {label} ({values.length})
      </h4>
      {values.length === 0 ? (
        <p className="mt-2 text-sm text-[#626f86]">Нет элементов.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {values.map((value, index) => (
            <li
              className="rounded-[10px] border border-[rgba(9,30,66,0.08)] bg-white px-3 py-2 text-sm text-[#44546f]"
              key={`${label}-${index}`}
            >
              {typeof value === "string"
                ? value
                : shortText(compactJson(value), 260)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function JsonDetails({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-4">
      <summary className="cursor-pointer text-sm font-semibold text-[#172b4d]">
        {label}
      </summary>
      <pre className="mt-3 max-h-96 overflow-auto rounded-[10px] bg-white p-3 text-xs leading-5 text-[#172b4d]">
        {compactJson(value)}
      </pre>
    </details>
  );
}
