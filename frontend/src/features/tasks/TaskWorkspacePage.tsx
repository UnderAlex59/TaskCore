import {
  useEffect,
  useEffectEvent,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";

import {
  chatApi,
  type ChatRealtimeEvent,
  type MessageRead,
} from "@/api/chatApi";
import { projectsApi, type ProjectMemberRead } from "@/api/projectsApi";
import { proposalsApi, type ProposalRead } from "@/api/proposalsApi";
import { taskTagsApi, type TaskTagOption } from "@/api/taskTagsApi";
import {
  tasksApi,
  type TaskAttachmentRead,
  type TaskRead,
  type TaskUpdate,
} from "@/api/tasksApi";
import ChatWindow from "@/features/chat/ChatWindow";
import TaskForm from "@/features/tasks/TaskForm";
import ValidationPanel from "@/features/tasks/ValidationPanel";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import {
  formatCountLabel,
  formatDateTime,
  getProposalStatusLabel,
  getRoleLabel,
  getTaskStatusLabel,
} from "@/shared/lib/locale";
import { useAuthStore } from "@/store/authStore";

interface Props {
  mode: "chat" | "detail";
}

type WorkspaceTab = "document" | "chat" | "history";

function canUserAccessChat(task: TaskRead, userId?: string, role?: string) {
  if (!userId || !role) {
    return false;
  }
  if (role === "ADMIN") {
    return true;
  }
  if (task.analyst_id === userId) {
    return true;
  }
  if (task.reviewer_analyst_id === userId) {
    return true;
  }

  const teamChatStatuses = new Set([
    "ready_for_dev",
    "in_progress",
    "ready_for_testing",
    "testing",
    "done",
  ]);
  if (!teamChatStatuses.has(task.status)) {
    return false;
  }

  return task.developer_id === userId || task.tester_id === userId;
}

function mergeMessages(current: MessageRead[], incoming: MessageRead[]) {
  const merged = new Map(current.map((message) => [message.id, message]));
  for (const message of incoming) {
    merged.set(message.id, message);
  }

  return [...merged.values()].sort((left, right) => {
    const timestampDiff =
      new Date(left.created_at).getTime() -
      new Date(right.created_at).getTime();
    if (timestampDiff !== 0) {
      return timestampDiff;
    }
    return left.id.localeCompare(right.id);
  });
}

function shouldShowAgentPending(message: MessageRead) {
  if (message.author_id === null) {
    return false;
  }

  return (
    message.message_type === "question" ||
    message.message_type === "change_proposal" ||
    message.content.trim().startsWith("/")
  );
}

function InspectorCard({
  children,
  title,
  eyebrow,
}: {
  children: ReactNode;
  eyebrow?: string;
  title: string;
}) {
  return (
    <section className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white p-5 shadow-[0_1px_2px_rgba(9,30,66,0.06)]">
      {eyebrow ? (
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
          {eyebrow}
        </p>
      ) : null}
      <h3 className="text-anywhere mt-2 text-lg font-semibold text-[#172b4d]">
        {title}
      </h3>
      <div className="mt-4 min-w-0">{children}</div>
    </section>
  );
}

export default function TaskWorkspacePage({ mode }: Props) {
  const { projectId, taskId } = useParams();
  const navigate = useNavigate();
  const accessToken = useAuthStore((state) => state.accessToken);
  const user = useAuthStore((state) => state.user);

  const [task, setTask] = useState<TaskRead | null>(null);
  const [taskTags, setTaskTags] = useState<TaskTagOption[]>([]);
  const [members, setMembers] = useState<ProjectMemberRead[]>([]);
  const [messages, setMessages] = useState<MessageRead[]>([]);
  const [proposals, setProposals] = useState<ProposalRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingTask, setSavingTask] = useState(false);
  const [suggestingTags, setSuggestingTags] = useState(false);
  const [committingTask, setCommittingTask] = useState(false);
  const [validating, setValidating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingTask, setDeletingTask] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [agentPendingMessageId, setAgentPendingMessageId] = useState<
    string | null
  >(null);
  const [taskPendingDeletion, setTaskPendingDeletion] = useState(false);
  const [reviewingProposalId, setReviewingProposalId] = useState<string | null>(
    null,
  );
  const [approving, setApproving] = useState(false);
  const [workflowActionPending, setWorkflowActionPending] = useState<
    "startDevelopment" | "readyForTesting" | "startTesting" | "complete" | null
  >(null);
  const [developerSelection, setDeveloperSelection] = useState("");
  const [testerSelection, setTesterSelection] = useState("");
  const [reviewerSelection, setReviewerSelection] = useState("");
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(
    mode === "chat" ? "chat" : "document",
  );

  const developerMembers = useMemo(
    () => members.filter((member) => member.role === "DEVELOPER"),
    [members],
  );
  const testerMembers = useMemo(
    () => members.filter((member) => member.role === "TESTER"),
    [members],
  );
  const reviewerMembers = useMemo(
    () =>
      members.filter(
        (member) =>
          member.role === "ANALYST" && member.user_id !== task?.analyst_id,
      ),
    [members, task?.analyst_id],
  );
  const canConnectToChat = task
    ? canUserAccessChat(task, user?.id, user?.role)
    : false;
  const agentPendingMessage = useMemo(() => {
    if (!agentPendingMessageId) {
      return null;
    }

    const pendingIndex = messages.findIndex(
      (message) => message.id === agentPendingMessageId,
    );
    if (pendingIndex < 0) {
      return null;
    }

    const hasAgentResponse = messages
      .slice(pendingIndex + 1)
      .some((message) => message.author_id === null);

    return hasAgentResponse ? null : messages[pendingIndex];
  }, [agentPendingMessageId, messages]);

  useEffect(() => {
    setDeveloperSelection(task?.developer_id ?? "");
    setTesterSelection(task?.tester_id ?? "");
    setReviewerSelection(task?.reviewer_analyst_id ?? "");
  }, [task?.developer_id, task?.reviewer_analyst_id, task?.tester_id]);

  useEffect(() => {
    setActiveTab(mode === "chat" ? "chat" : "document");
  }, [mode, taskId]);

  async function loadData() {
    if (!projectId || !taskId) {
      setError("Не найден идентификатор задачи.");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const [loadedTask, loadedMembers, loadedProposals, loadedTaskTags] =
        await Promise.all([
          tasksApi.get(projectId, taskId),
          projectsApi.listMembers(projectId),
          proposalsApi.list(taskId),
          taskTagsApi.list(projectId),
        ]);

      setTask(loadedTask);
      setTaskTags(loadedTaskTags);
      setMembers(loadedMembers);
      setProposals(loadedProposals);

      if (canUserAccessChat(loadedTask, user?.id, user?.role)) {
        setMessages(await chatApi.list(taskId, { limit: 100 }));
      } else {
        setMessages([]);
      }
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить задачу."));
    } finally {
      setLoading(false);
    }
  }

  const onLoadData = useEffectEvent(loadData);

  useEffect(() => {
    void onLoadData();
  }, [projectId, taskId, user?.id, user?.role]); // eslint-disable-line react-hooks/exhaustive-deps

  async function refreshTaskAndMessages() {
    if (!projectId || !taskId) {
      return;
    }

    const loadedTask = await tasksApi.get(projectId, taskId);
    setTask(loadedTask);

    if (canUserAccessChat(loadedTask, user?.id, user?.role)) {
      setMessages(await chatApi.list(taskId, { limit: 100 }));
    } else {
      setMessages([]);
    }
  }

  async function refreshTaskSnapshot() {
    if (!projectId || !taskId) {
      return;
    }

    setTask(await tasksApi.get(projectId, taskId));
  }

  async function handleSave(payload: TaskUpdate) {
    if (!projectId || !taskId) {
      return;
    }

    try {
      setSavingTask(true);
      setError(null);
      setTask(await tasksApi.update(projectId, taskId, payload));
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось сохранить задачу."));
    } finally {
      setSavingTask(false);
    }
  }

  async function handleSuggestTags(payload: {
    title: string;
    content: string;
    current_tags: string[];
  }) {
    if (!projectId || !taskId) {
      throw new Error("Missing project or task id");
    }

    try {
      setSuggestingTags(true);
      setError(null);
      return await tasksApi.suggestTags(projectId, taskId, payload);
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось подобрать теги для текущей версии задачи.",
        ),
      );
      throw caught;
    } finally {
      setSuggestingTags(false);
    }
  }

  async function handleCommitTaskChanges() {
    if (!projectId || !taskId) {
      return;
    }

    try {
      setCommittingTask(true);
      setError(null);
      setTask(await tasksApi.commitChanges(projectId, taskId));
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось выполнить commit изменений."),
      );
    } finally {
      setCommittingTask(false);
    }
  }

  async function handleValidate() {
    if (!taskId) {
      return;
    }

    try {
      setValidating(true);
      setError(null);
      await tasksApi.validate(taskId);
      await refreshTaskAndMessages();
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось запустить проверку."));
    } finally {
      setValidating(false);
    }
  }

  async function handleApprove() {
    if (!projectId || !taskId) {
      return;
    }

    try {
      setApproving(true);
      setError(null);
      const approvedTask = await tasksApi.approve(projectId, taskId, {
        developer_id: developerSelection,
        reviewer_analyst_id: reviewerSelection || null,
        tester_id: testerSelection,
      });
      setTask(approvedTask);
      await refreshTaskAndMessages();
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось завершить этап аналитического ревью.",
        ),
      );
    } finally {
      setApproving(false);
    }
  }

  async function handleWorkflowTransition(
    action:
      | "startDevelopment"
      | "readyForTesting"
      | "startTesting"
      | "complete",
  ) {
    if (!projectId || !taskId) {
      return;
    }

    const actionMap = {
      complete: tasksApi.complete,
      readyForTesting: tasksApi.markReadyForTesting,
      startDevelopment: tasksApi.startDevelopment,
      startTesting: tasksApi.startTesting,
    } as const;
    const fallbackMessages = {
      complete: "Не удалось завершить задачу.",
      readyForTesting:
        "Не удалось перевести задачу в статус готово к тестированию.",
      startDevelopment: "Не удалось взять задачу в разработку.",
      startTesting: "Не удалось взять задачу в тестирование.",
    } as const;

    try {
      setWorkflowActionPending(action);
      setError(null);
      setTask(await actionMap[action](projectId, taskId));
      await refreshTaskAndMessages();
    } catch (caught) {
      setError(getApiErrorMessage(caught, fallbackMessages[action]));
    } finally {
      setWorkflowActionPending(null);
    }
  }

  async function handleUpload(file: File) {
    if (!projectId || !taskId) {
      return;
    }

    try {
      setUploading(true);
      setError(null);
      await tasksApi.uploadAttachment(projectId, taskId, file);
      setTask(await tasksApi.get(projectId, taskId));
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить вложение."));
    } finally {
      setUploading(false);
    }
  }

  async function handleOpenAttachment(attachment: TaskAttachmentRead) {
    if (!projectId || !taskId) {
      throw new Error("Task route params are missing.");
    }

    return tasksApi.getAttachmentBlob(projectId, taskId, attachment.id);
  }

  async function handleDeleteAttachment(attachment: TaskAttachmentRead) {
    if (!projectId || !taskId) {
      return;
    }

    try {
      setError(null);
      await tasksApi.deleteAttachment(projectId, taskId, attachment.id);
      setTask(await tasksApi.get(projectId, taskId));
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить вложение."));
      throw caught;
    }
  }

  async function handleDeleteTask() {
    if (!projectId || !taskId) {
      return;
    }

    try {
      setDeletingTask(true);
      setError(null);
      await tasksApi.remove(projectId, taskId);
      navigate(`/projects/${projectId}/tasks`, { replace: true });
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить задачу."));
    } finally {
      setDeletingTask(false);
    }
  }

  async function handleSendMessage(content: string) {
    if (!taskId) {
      return;
    }

    try {
      setSendingMessage(true);
      setError(null);
      const created = await chatApi.send(taskId, { content });
      setMessages((current) => mergeMessages(current, created));
      setAgentPendingMessageId(
        [...created].reverse().find(shouldShowAgentPending)?.id ?? null,
      );

      if (
        created.some((message) => message.message_type === "agent_proposal")
      ) {
        setProposals(await proposalsApi.list(taskId));
      }
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось отправить сообщение."));
    } finally {
      setSendingMessage(false);
    }
  }

  async function handleProposalReview(
    proposalId: string,
    status: "accepted" | "rejected",
  ) {
    if (!taskId) {
      return;
    }

    try {
      setReviewingProposalId(proposalId);
      setError(null);
      await proposalsApi.update(taskId, proposalId, { status });
      const [loadedProposals] = await Promise.all([
        proposalsApi.list(taskId),
        refreshTaskAndMessages(),
      ]);
      setProposals(loadedProposals);
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось обработать предложение."),
      );
    } finally {
      setReviewingProposalId(null);
    }
  }

  const onRealtimeMessages = useEffectEvent(async (incoming: MessageRead[]) => {
    setMessages((current) => mergeMessages(current, incoming));
    if (incoming.some((message) => message.author_id === null)) {
      setAgentPendingMessageId(null);
    }

    if (!taskId) {
      return;
    }

    if (incoming.some((message) => message.message_type === "agent_proposal")) {
      setProposals(await proposalsApi.list(taskId));
    }

    if (
      incoming.some(
        (message) =>
          message.author_id === null &&
          (message.agent_name === "ManagerAgent" ||
            message.agent_name === "QAAgent" ||
            message.source_ref?.collection === "tasks"),
      )
    ) {
      await refreshTaskSnapshot();
    }
  });

  useEffect(() => {
    if (!taskId || !accessToken || !canConnectToChat) {
      return;
    }

    let reconnectTimer: number | null = null;
    let socket: WebSocket | null = null;
    let isClosed = false;

    const connect = () => {
      if (isClosed) {
        return;
      }

      socket = chatApi.connect(taskId, accessToken);
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as ChatRealtimeEvent;
          if (
            payload.type === "messages.created" &&
            Array.isArray(payload.messages)
          ) {
            void onRealtimeMessages(payload.messages);
          }
        } catch {
          // Ignore malformed realtime payloads and keep the connection alive.
        }
      };
      socket.onclose = () => {
        if (isClosed) {
          return;
        }

        reconnectTimer = window.setTimeout(connect, 1500);
      };
    };

    connect();

    return () => {
      isClosed = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [accessToken, canConnectToChat, onRealtimeMessages, taskId]);

  if (loading) {
    return <LoadingSpinner label="Загрузка задачи" />;
  }

  if (!task || !projectId || !taskId) {
    return (
      <section className="glass-panel p-6 sm:p-8">
        <p aria-live="polite" className="text-sm text-red-700">
          {error ?? "Задача не найдена."}
        </p>
      </section>
    );
  }

  const canAccessChat = canUserAccessChat(task, user?.id, user?.role);
  const editableStatuses = new Set([
    "draft",
    "needs_rework",
    "awaiting_approval",
    "ready_for_dev",
    "in_progress",
    "ready_for_testing",
    "testing",
    "done",
  ]);
  const postApprovalStatuses = new Set([
    "ready_for_dev",
    "in_progress",
    "ready_for_testing",
    "testing",
    "done",
  ]);
  const hasApprovalRole = user?.role === "ADMIN" || user?.role === "ANALYST";
  const hasReviewRole = hasApprovalRole || user?.role === "MANAGER";
  const canRunPostApprovalRevalidation =
    task.requires_revalidation &&
    postApprovalStatuses.has(task.status) &&
    !task.embeddings_stale;
  const validationBlockedReason =
    task.requires_revalidation &&
    postApprovalStatuses.has(task.status) &&
    task.embeddings_stale
      ? "Сначала выполните commit изменений, чтобы пересчитать эмбеддинги. " +
        "После этого задачу можно отправить на повторную проверку."
      : undefined;
  const canEditTask = hasApprovalRole && editableStatuses.has(task.status);
  const canValidate =
    hasApprovalRole &&
    (task.status === "draft" ||
      task.status === "needs_rework" ||
      canRunPostApprovalRevalidation);
  const canApprove = hasReviewRole && task.status === "awaiting_approval";
  const canConfigureApproval =
    canApprove &&
    (user?.role === "ADMIN" ||
      user?.role === "MANAGER" ||
      user?.id === task.analyst_id);
  const canReviewProposals = hasApprovalRole;
  const canDeleteTask = user?.role === "ADMIN";
  const canCommitTask =
    canEditTask && task.status !== "validating" && task.embeddings_stale;
  const needsManualCommit =
    [
      "ready_for_dev",
      "in_progress",
      "ready_for_testing",
      "testing",
      "done",
    ].includes(task.status) && task.embeddings_stale;
  const detailHref = `/projects/${projectId}/tasks/${taskId}`;
  const tasksHref = `/projects/${projectId}/tasks`;

  if (mode === "chat" && !canAccessChat) {
    return <Navigate replace to={detailHref} />;
  }

  const membersById = new Map(
    members.map((member) => [member.user_id, member]),
  );
  const analyst = membersById.get(task.analyst_id);
  const reviewer = task.reviewer_analyst_id
    ? membersById.get(task.reviewer_analyst_id)
    : null;
  const developer = task.developer_id
    ? membersById.get(task.developer_id)
    : null;
  const tester = task.tester_id ? membersById.get(task.tester_id) : null;
  const secondReviewPending =
    Boolean(task.reviewer_analyst_id) && !task.reviewer_approved_at;
  const canStartDevelopment =
    user?.id === task.developer_id && task.status === "ready_for_dev";
  const canMarkReadyForTesting =
    user?.id === task.developer_id && task.status === "in_progress";
  const canStartTesting =
    user?.id === task.tester_id && task.status === "ready_for_testing";
  const canCompleteTask =
    user?.id === task.tester_id && task.status === "testing";
  const approvalButtonLabel = secondReviewPending
    ? "Сохранить состав и отправить на второе ревью"
    : task.reviewer_analyst_id && task.reviewer_approved_at
      ? "Открыть разработку"
      : "Подтвердить и назначить";

  const teamCards = [
    {
      key: "analyst",
      title: "Аналитик",
      member: analyst,
      fallback: "Назначается автоматически при создании задачи.",
    },
    {
      key: "reviewer",
      title: "Второй аналитик",
      member: reviewer,
      fallback: "Не требуется для этой задачи.",
    },
    {
      key: "developer",
      title: "Разработчик",
      member: developer,
      fallback: "Будет назначен после подтверждения.",
    },
    {
      key: "tester",
      title: "Тестировщик",
      member: tester,
      fallback: "Будет назначен после подтверждения.",
    },
  ];

  const workspaceTabs: Array<{
    key: WorkspaceTab;
    label: string;
    disabled?: boolean;
  }> = [
    { key: "document", label: "Задача" },
    { key: "chat", label: "Чат", disabled: !canAccessChat },
    { key: "history", label: "История изменений" },
  ];

  const chatSection = canAccessChat ? (
    <ChatWindow
      agentPendingMessage={agentPendingMessage}
      className="h-full"
      compactInput
      currentUserId={user?.id}
      description="Рабочее обсуждение задачи: уточнения, решения, изменения и вопросы агенту."
      disabled={!canAccessChat}
      inputPlaceholder="Напишите вопрос по задаче, решение или команду для агента..."
      messages={messages}
      onSend={handleSendMessage}
      sending={sendingMessage}
      title="Чат задачи"
    />
  ) : (
    <article className="rounded-[16px] border border-dashed border-[rgba(9,30,66,0.12)] bg-white px-5 py-6 text-sm leading-7 text-[#44546f]">
      Чат откроется после формирования команды задачи. До этого обсуждение
      доступно аналитику, второму аналитику при назначении и администратору.
    </article>
  );

  return (
    <section
      className={
        activeTab === "chat"
          ? "flex h-[calc(100svh-6.625rem)] min-w-0 flex-col gap-3 overflow-hidden sm:h-[calc(100svh-7.625rem)] lg:h-[calc(100svh-3rem)]"
          : "min-w-0 space-y-5"
      }
    >
      <header
        className={[
          "shrink-0 rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white shadow-[0_1px_2px_rgba(9,30,66,0.06)]",
          activeTab === "chat" ? "px-4 py-3 sm:px-5" : "px-6 py-5",
        ].join(" ")}
      >
        <div
          className={
            activeTab === "chat"
              ? "flex flex-col gap-2"
              : "flex flex-col gap-5"
          }
        >
          <div
            className={
              activeTab === "chat"
                ? "hidden"
                : "flex flex-wrap items-center gap-2 text-sm text-[#626f86]"
            }
          >
            <Link className="hover:text-[#0c66e4]" to={tasksHref}>
              Задачи
            </Link>
            <span>/</span>
            <span>Карточка задачи</span>
          </div>

          <div
            className={
              activeTab === "chat"
                ? "flex min-w-0 items-start justify-between gap-3"
                : "flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between"
            }
          >
            <div className="min-w-0">
              <p
                className={
                  activeTab === "chat" ? "hidden" : "section-eyebrow"
                }
              >
                Рабочая область задачи
              </p>
              <h2
                className={[
                  "text-anywhere mt-2 text-balance font-semibold leading-tight text-[#172b4d]",
                  activeTab === "chat"
                    ? "mt-0 line-clamp-1 text-xl sm:text-2xl"
                    : "text-3xl sm:text-[2.25rem]",
                ].join(" ")}
              >
                {task.title}
              </h2>
              <p
                className={
                  activeTab === "chat"
                    ? "hidden"
                    : "text-anywhere mt-3 max-w-4xl text-sm leading-7 text-[#44546f]"
                }
              >
                Пространство разделено на три рабочие вкладки: основной текст
                задачи, чат по задаче и история изменений. Это убирает
                перегрузку и позволяет работать с каждым контекстом отдельно.
              </p>
            </div>
            {canDeleteTask ? (
              <button
                className={
                  activeTab === "chat"
                    ? "ui-button-danger hidden shrink-0 sm:inline-flex"
                    : "ui-button-danger shrink-0"
                }
                disabled={deletingTask}
                onClick={() => setTaskPendingDeletion(true)}
                type="button"
              >
                {deletingTask ? "Удаляем..." : "Удалить задачу"}
              </button>
            ) : null}
          </div>

          <div
            className={
              activeTab === "chat"
                ? "hidden"
                : "flex min-w-0 flex-wrap gap-2 text-xs font-medium text-[#44546f]"
            }
          >
            <span className="text-anywhere max-w-full rounded-full bg-[#e9f2ff] px-3 py-1.5 text-[#0c66e4]">
              {getTaskStatusLabel(task.status)}
            </span>
            <span className="text-anywhere max-w-full rounded-full bg-[#f7f8fa] px-3 py-1.5">
              {formatCountLabel(
                proposals.length,
                "предложение",
                "предложения",
                "предложений",
              )}
            </span>
            <span className="text-anywhere max-w-full rounded-full bg-[#f7f8fa] px-3 py-1.5">
              {formatCountLabel(
                messages.length,
                "сообщение",
                "сообщения",
                "сообщений",
              )}
            </span>
            <span className="text-anywhere max-w-full rounded-full bg-[#f7f8fa] px-3 py-1.5">
              Обновлено {formatDateTime(task.updated_at)}
            </span>
            {needsManualCommit ? (
              <span className="text-anywhere max-w-full rounded-full bg-[#e9f2ff] px-3 py-1.5 text-[#0c66e4]">
                Требуется commit
              </span>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-2">
            {workspaceTabs.map((tab) => (
              <button
                key={tab.key}
                className={
                  activeTab === tab.key
                    ? "rounded-[10px] border border-[#bfd4f6] bg-[#e9f2ff] px-3 py-2 text-sm font-medium text-[#0c66e4] sm:px-4"
                    : "rounded-[10px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] px-3 py-2 text-sm font-medium text-[#44546f] hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 sm:px-4"
                }
                disabled={tab.disabled}
                onClick={() => setActiveTab(tab.key)}
                type="button"
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {error ? (
        <p
          aria-live="polite"
          className="shrink-0 rounded-[14px] border border-[rgba(174,46,36,0.16)] bg-[#fdecec] px-4 py-3 text-sm text-[#ae2e24]"
        >
          {error}
        </p>
      ) : null}

      <div className={activeTab === "chat" ? "hidden" : "space-y-5"}>
        <TaskForm
          activePane={activeTab === "history" ? "history" : "document"}
          attachments={task.attachments}
          attachmentsUploading={uploading}
          availableTags={taskTags}
          canCommitChanges={canCommitTask}
          canSuggestTags={canEditTask && activeTab !== "history"}
          committing={committingTask}
          disabled={!canEditTask}
          embeddingsStale={task.embeddings_stale}
          loading={savingTask}
          onCommit={handleCommitTaskChanges}
          onDeleteAttachment={handleDeleteAttachment}
          onOpenAttachment={handleOpenAttachment}
          onSuggestTags={handleSuggestTags}
          onSubmit={handleSave}
          onUploadAttachment={handleUpload}
          suggestingTags={suggestingTags}
          task={task}
        />

        {activeTab === "document" ? (
          <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)]">
            <InspectorCard eyebrow="Процесс" title="Проверка требования">
              <ValidationPanel
                blockedReason={validationBlockedReason}
                canValidate={canValidate}
                onValidate={handleValidate}
                requiresRevalidation={task.requires_revalidation}
                result={task.validation_result}
                validating={validating}
              />
            </InspectorCard>

            <div className="min-w-0 space-y-5">
              <InspectorCard eyebrow="Команда" title="Участники задачи">
                <div className="min-w-0 space-y-3">
                  {teamCards.map((item) => (
                    <article
                      key={item.key}
                      className="min-w-0 rounded-[14px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] px-4 py-3"
                    >
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                        {item.title}
                      </p>
                      {item.member ? (
                        <>
                          <p className="text-anywhere mt-2 font-medium text-[#172b4d]">
                            {item.member.full_name}
                          </p>
                          <p className="text-anywhere mt-1 text-sm text-[#44546f]">
                            {item.member.email} /{" "}
                            {getRoleLabel(item.member.role)}
                          </p>
                        </>
                      ) : (
                        <p className="text-anywhere mt-2 text-sm leading-6 text-[#626f86]">
                          {item.fallback}
                        </p>
                      )}
                    </article>
                  ))}
                </div>

                {canConfigureApproval ? (
                  <div className="mt-5 space-y-4 rounded-[14px] border border-[rgba(172,107,8,0.18)] bg-[#fff4e5] p-4">
                    <div>
                      <p className="text-sm font-semibold text-[#172b4d]">
                        Подтверждение после review
                      </p>
                      <p className="mt-1 text-sm leading-6 text-[#7f4c00]">
                        Назначьте команду и при необходимости укажите второго
                        аналитика. Статус `Готово к разработке` появится только
                        после всех обязательных ревью.
                      </p>
                    </div>
                    <label className="block">
                      <span className="mb-2 block text-sm font-medium text-[#172b4d]">
                        Второй аналитик
                      </span>
                      <select
                        className="ui-field"
                        onChange={(event) =>
                          setReviewerSelection(event.target.value)
                        }
                        value={reviewerSelection}
                      >
                        <option value="">Без второго ревью</option>
                        {reviewerMembers.map((member) => (
                          <option key={member.user_id} value={member.user_id}>
                            {member.full_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block">
                      <span className="mb-2 block text-sm font-medium text-[#172b4d]">
                        Разработчик
                      </span>
                      <select
                        className="ui-field"
                        onChange={(event) =>
                          setDeveloperSelection(event.target.value)
                        }
                        value={developerSelection}
                      >
                        <option value="">Выберите разработчика</option>
                        {developerMembers.map((member) => (
                          <option key={member.user_id} value={member.user_id}>
                            {member.full_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block">
                      <span className="mb-2 block text-sm font-medium text-[#172b4d]">
                        Тестировщик
                      </span>
                      <select
                        className="ui-field"
                        onChange={(event) =>
                          setTesterSelection(event.target.value)
                        }
                        value={testerSelection}
                      >
                        <option value="">Выберите тестировщика</option>
                        {testerMembers.map((member) => (
                          <option key={member.user_id} value={member.user_id}>
                            {member.full_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="ui-button-primary w-full"
                      disabled={
                        approving || !developerSelection || !testerSelection
                      }
                      onClick={() => void handleApprove()}
                      type="button"
                    >
                      {approving ? "Сохраняем маршрут..." : approvalButtonLabel}
                    </button>
                    {secondReviewPending && reviewer ? (
                      <p className="text-sm leading-6 text-[#7f4c00]">
                        Ожидается подтверждение второго аналитика:{" "}
                        <span className="font-medium text-[#172b4d]">
                          {reviewer.full_name}
                        </span>
                        .
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {user?.id === task.reviewer_analyst_id &&
                task.status === "awaiting_approval" &&
                !task.reviewer_approved_at ? (
                  <div className="mt-5 space-y-3 rounded-[14px] border border-[rgba(12,102,228,0.16)] bg-[#e9f2ff] p-4">
                    <div>
                      <p className="text-sm font-semibold text-[#172b4d]">
                        Второе аналитическое ревью
                      </p>
                      <p className="mt-1 text-sm leading-6 text-[#44546f]">
                        После вашего подтверждения задача станет готовой к
                        разработке, если команда уже назначена.
                      </p>
                    </div>
                    <button
                      className="ui-button-primary w-full"
                      disabled={approving}
                      onClick={() => void handleApprove()}
                      type="button"
                    >
                      {approving
                        ? "Подтверждаем ревью..."
                        : "Подтвердить второе ревью"}
                    </button>
                  </div>
                ) : null}

                {canStartDevelopment ||
                canMarkReadyForTesting ||
                canStartTesting ||
                canCompleteTask ? (
                  <div className="mt-5 space-y-3 rounded-[14px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-4">
                    <div>
                      <p className="text-sm font-semibold text-[#172b4d]">
                        Переход по workflow
                      </p>
                      <p className="mt-1 text-sm leading-6 text-[#44546f]">
                        Кнопки доступны только ответственному участнику на
                        текущем этапе.
                      </p>
                    </div>
                    {canStartDevelopment ? (
                      <button
                        className="ui-button-primary w-full"
                        disabled={workflowActionPending !== null}
                        onClick={() =>
                          void handleWorkflowTransition("startDevelopment")
                        }
                        type="button"
                      >
                        {workflowActionPending === "startDevelopment"
                          ? "Берём в разработку..."
                          : "Взять в разработку"}
                      </button>
                    ) : null}
                    {canMarkReadyForTesting ? (
                      <button
                        className="ui-button-primary w-full"
                        disabled={workflowActionPending !== null}
                        onClick={() =>
                          void handleWorkflowTransition("readyForTesting")
                        }
                        type="button"
                      >
                        {workflowActionPending === "readyForTesting"
                          ? "Переводим..."
                          : "Готово к тестированию"}
                      </button>
                    ) : null}
                    {canStartTesting ? (
                      <button
                        className="ui-button-primary w-full"
                        disabled={workflowActionPending !== null}
                        onClick={() =>
                          void handleWorkflowTransition("startTesting")
                        }
                        type="button"
                      >
                        {workflowActionPending === "startTesting"
                          ? "Запускаем тестирование..."
                          : "Взять в тестирование"}
                      </button>
                    ) : null}
                    {canCompleteTask ? (
                      <button
                        className="ui-button-primary w-full"
                        disabled={workflowActionPending !== null}
                        onClick={() =>
                          void handleWorkflowTransition("complete")
                        }
                        type="button"
                      >
                        {workflowActionPending === "complete"
                          ? "Завершаем..."
                          : "Задача выполнена"}
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </InspectorCard>

              <InspectorCard
                eyebrow="Изменения"
                title="Предложения по изменениям"
              >
                <div className="min-w-0 space-y-3">
                  {proposals.length === 0 ? (
                    <p className="text-sm leading-6 text-[#626f86]">
                      Предложений по изменениям пока нет.
                    </p>
                  ) : (
                    proposals.map((proposal) => (
                      <article
                        key={proposal.id}
                        className="min-w-0 rounded-[14px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-4"
                      >
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                          {getProposalStatusLabel(proposal.status)}
                        </p>
                        <p className="text-anywhere mt-2 text-sm leading-7 text-[#172b4d]">
                          {proposal.proposal_text}
                        </p>
                        <p className="text-anywhere mt-2 text-xs leading-5 text-[#626f86]">
                          Предложил:{" "}
                          {proposal.proposed_by_name ??
                            "неизвестный пользователь"}
                          .
                          {proposal.reviewed_by_name
                            ? ` Рассмотрел: ${proposal.reviewed_by_name}.`
                            : ""}
                        </p>
                        {canReviewProposals && proposal.status === "new" ? (
                          <div className="mt-3 flex min-w-0 flex-wrap gap-2">
                            <button
                              className="ui-button-primary"
                              disabled={reviewingProposalId === proposal.id}
                              onClick={() =>
                                void handleProposalReview(
                                  proposal.id,
                                  "accepted",
                                )
                              }
                              type="button"
                            >
                              Принять
                            </button>
                            <button
                              className="ui-button-secondary"
                              disabled={reviewingProposalId === proposal.id}
                              onClick={() =>
                                void handleProposalReview(
                                  proposal.id,
                                  "rejected",
                                )
                              }
                              type="button"
                            >
                              Отклонить
                            </button>
                          </div>
                        ) : null}
                      </article>
                    ))
                  )}
                </div>
              </InspectorCard>
            </div>
          </div>
        ) : (
          <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <InspectorCard eyebrow="Публикация" title="Состояние публикации">
              <div className="text-anywhere min-w-0 space-y-3 text-sm leading-7 text-[#44546f]">
                <p>
                  Последняя правка карточки:
                  <span className="ml-2 font-medium text-[#172b4d]">
                    {formatDateTime(task.updated_at)}
                  </span>
                </p>
                <p>
                  Последний пересчет индекса:
                  <span className="ml-2 font-medium text-[#172b4d]">
                    {task.indexed_at
                      ? formatDateTime(task.indexed_at)
                      : "еще не выполнялся"}
                  </span>
                </p>
                <div
                  className={
                    task.embeddings_stale
                      ? "rounded-[14px] border border-[rgba(12,102,228,0.16)] bg-[#e9f2ff] px-4 py-3 text-[#0c66e4]"
                      : "rounded-[14px] border border-[rgba(34,154,22,0.14)] bg-[#e8f5e9] px-4 py-3 text-[#216e1f]"
                  }
                >
                  {task.embeddings_stale
                    ? "Текст уже обновлен, но индекс еще использует предыдущую опубликованную версию."
                    : "Карточка задачи и индекс синхронизированы."}
                </div>
              </div>
            </InspectorCard>

            <InspectorCard eyebrow="Контекст" title="Команда и ревью">
              <div className="space-y-4">
                <div className="grid min-w-0 gap-3 md:grid-cols-3">
                  {teamCards.map((item) => (
                    <article
                      key={item.key}
                      className="min-w-0 rounded-[14px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] px-4 py-3"
                    >
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                        {item.title}
                      </p>
                      <p className="text-anywhere mt-2 text-sm leading-6 text-[#172b4d]">
                        {item.member?.full_name ?? item.fallback}
                      </p>
                    </article>
                  ))}
                </div>
                <div className="rounded-[14px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] px-4 py-3 text-sm leading-7 text-[#44546f]">
                  <p>
                    Предложений по изменениям:{" "}
                    <span className="font-medium text-[#172b4d]">
                      {proposals.length}
                    </span>
                  </p>
                  <p>
                    Текущий статус задачи:{" "}
                    <span className="font-medium text-[#172b4d]">
                      {getTaskStatusLabel(task.status)}
                    </span>
                  </p>
                </div>
              </div>
            </InspectorCard>
          </div>
        )}
      </div>

      {activeTab === "chat" ? (
        <div className="min-h-0 flex-1">{chatSection}</div>
      ) : null}

      <ConfirmDialog
        busy={deletingTask}
        confirmLabel="Удалить задачу"
        description={`Удалить задачу «${task.title}»? История, вложения и индекс задачи будут удалены.`}
        destructive
        onClose={() => {
          if (!deletingTask) {
            setTaskPendingDeletion(false);
          }
        }}
        onConfirm={handleDeleteTask}
        open={taskPendingDeletion}
        title="Удаление задачи"
      />
    </section>
  );
}
