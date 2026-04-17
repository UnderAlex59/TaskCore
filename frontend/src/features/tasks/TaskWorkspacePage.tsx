import { useEffect, useEffectEvent, useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { chatApi, type MessageRead } from "@/api/chatApi";
import { projectsApi, type ProjectMemberRead } from "@/api/projectsApi";
import { proposalsApi, type ProposalRead } from "@/api/proposalsApi";
import { tasksApi, type TaskRead, type TaskUpdate } from "@/api/tasksApi";
import ChatWindow from "@/features/chat/ChatWindow";
import AttachmentUpload from "@/features/tasks/AttachmentUpload";
import TaskForm from "@/features/tasks/TaskForm";
import ValidationPanel from "@/features/tasks/ValidationPanel";
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

  const teamChatStatuses = new Set(["ready_for_dev", "in_progress", "done"]);
  if (!teamChatStatuses.has(task.status)) {
    return false;
  }

  return task.developer_id === userId || task.tester_id === userId;
}

export default function TaskWorkspacePage({ mode }: Props) {
  const { projectId, taskId } = useParams();
  const user = useAuthStore((state) => state.user);

  const [task, setTask] = useState<TaskRead | null>(null);
  const [members, setMembers] = useState<ProjectMemberRead[]>([]);
  const [messages, setMessages] = useState<MessageRead[]>([]);
  const [proposals, setProposals] = useState<ProposalRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingTask, setSavingTask] = useState(false);
  const [validating, setValidating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [reviewingProposalId, setReviewingProposalId] = useState<string | null>(
    null,
  );
  const [approving, setApproving] = useState(false);
  const [developerSelection, setDeveloperSelection] = useState("");
  const [testerSelection, setTesterSelection] = useState("");

  const developerMembers = useMemo(
    () => members.filter((member) => member.role === "DEVELOPER"),
    [members],
  );
  const testerMembers = useMemo(
    () => members.filter((member) => member.role === "TESTER"),
    [members],
  );

  useEffect(() => {
    setDeveloperSelection(task?.developer_id ?? "");
    setTesterSelection(task?.tester_id ?? "");
  }, [task?.developer_id, task?.tester_id]);

  async function loadData() {
    if (!projectId || !taskId) {
      setError("Не найден идентификатор задачи.");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const [loadedTask, loadedMembers, loadedProposals] = await Promise.all([
        tasksApi.get(projectId, taskId),
        projectsApi.listMembers(projectId),
        proposalsApi.list(taskId),
      ]);

      setTask(loadedTask);
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

  async function handleSave(payload: TaskUpdate) {
    if (!projectId || !taskId) {
      return;
    }

    try {
      setSavingTask(true);
      setTask(await tasksApi.update(projectId, taskId, payload));
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось сохранить задачу."));
    } finally {
      setSavingTask(false);
    }
  }

  async function handleValidate() {
    if (!taskId) {
      return;
    }

    try {
      setValidating(true);
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
      const approvedTask = await tasksApi.approve(projectId, taskId, {
        developer_id: developerSelection,
        tester_id: testerSelection,
      });
      setTask(approvedTask);
      await refreshTaskAndMessages();
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось сформировать команду задачи."));
    } finally {
      setApproving(false);
    }
  }

  async function handleUpload(file: File) {
    if (!projectId || !taskId) {
      return;
    }

    try {
      setUploading(true);
      await tasksApi.uploadAttachment(projectId, taskId, file);
      setTask(await tasksApi.get(projectId, taskId));
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить вложение."));
    } finally {
      setUploading(false);
    }
  }

  async function handleSendMessage(content: string) {
    if (!taskId) {
      return;
    }

    try {
      setSendingMessage(true);
      const created = await chatApi.send(taskId, { content });
      setMessages((current) => [...current, ...created]);

      if (created.some((message) => message.message_type === "agent_proposal")) {
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
      await proposalsApi.update(taskId, proposalId, { status });
      const [loadedProposals] = await Promise.all([
        proposalsApi.list(taskId),
        refreshTaskAndMessages(),
      ]);
      setProposals(loadedProposals);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось обработать предложение."));
    } finally {
      setReviewingProposalId(null);
    }
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка задачи" />;
  }

  if (!task || !projectId || !taskId) {
    return (
      <section className="glass-panel border border-black/10 p-6 shadow-panel sm:p-8">
        <p aria-live="polite" className="text-sm text-red-700">
          {error ?? "Задача не найдена."}
        </p>
      </section>
    );
  }

  const canAccessChat = canUserAccessChat(task, user?.id, user?.role);
  const canEditTask =
    (user?.role === "ADMIN" || user?.role === "ANALYST") &&
    (task.status === "draft" || task.status === "needs_rework");
  const canValidate =
    (user?.role === "ADMIN" || user?.role === "ANALYST") &&
    (task.status === "draft" || task.status === "needs_rework");
  const canApprove =
    (user?.role === "ADMIN" || user?.role === "ANALYST") &&
    task.status === "awaiting_approval";
  const canReviewProposals = user?.role === "ADMIN" || user?.role === "ANALYST";
  const fullChatHref = `/projects/${projectId}/tasks/${taskId}/chat`;
  const detailHref = `/projects/${projectId}/tasks/${taskId}`;

  if (mode === "chat" && !canAccessChat) {
    return <Navigate replace to={detailHref} />;
  }

  const membersById = new Map(members.map((member) => [member.user_id, member]));
  const analyst = membersById.get(task.analyst_id);
  const developer = task.developer_id ? membersById.get(task.developer_id) : null;
  const tester = task.tester_id ? membersById.get(task.tester_id) : null;

  const teamCards = [
    {
      key: "analyst",
      title: "Аналитик",
      member: analyst,
      fallback: "Назначается автоматически при создании задачи",
    },
    {
      key: "developer",
      title: "Разработчик",
      member: developer,
      fallback: "Будет назначен на этапе approve",
    },
    {
      key: "tester",
      title: "Тестировщик",
      member: tester,
      fallback: "Будет назначен на этапе approve",
    },
  ];

  const chatSection = canAccessChat ? (
    <ChatWindow
      actions={
        mode === "detail" ? (
          <Link className="ui-button-secondary" to={fullChatHref}>
            Полноэкранный режим
          </Link>
        ) : null
      }
      className={
        mode === "chat"
          ? "h-[calc(100svh-14rem)] max-h-[calc(100svh-14rem)] min-h-[calc(100svh-14rem)]"
          : "xl:h-[calc(100svh-13rem)] xl:max-h-[calc(100svh-13rem)] xl:min-h-[calc(100svh-13rem)]"
      }
      description={
        mode === "chat"
          ? "Общий чат задачи. До approve он доступен только аналитику, после формирования команды — всем участникам задачи."
          : "Единый чат задачи. История сохраняется при переходе от аналитической фазы к работе команды."
      }
      disabled={!canAccessChat}
      inputPlaceholder="Напишите вопрос, уточнение или изменение по задаче..."
      messages={messages}
      onSend={handleSendMessage}
      sending={sendingMessage}
      title={mode === "chat" ? "Полноэкранный диалог" : "Обсуждение задачи"}
    />
  ) : (
    <article className="glass-panel border border-dashed border-black/10 p-5 text-sm text-slate/70 shadow-panel sm:p-6">
      Чат откроется после формирования команды задачи. До этого сообщения доступны
      только аналитику и администратору.
    </article>
  );

  if (mode === "chat") {
    return (
      <section className="space-y-6">
        <header className="glass-panel border border-black/10 p-5 shadow-panel sm:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="section-eyebrow">Фокусный чат задачи</p>
              <h2 className="mt-3 text-balance text-3xl font-bold text-ink sm:text-4xl">
                {task.title}
              </h2>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-slate/80">
                Единый чат задачи сохраняет историю аналитической фазы и командной
                работы без отдельной ветки обсуждения.
              </p>
            </div>
            <Link className="ui-button-secondary" to={detailHref}>
              Вернуться к задаче
            </Link>
          </div>
          <div className="mt-5 flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate/70">
            <span className="rounded-[8px] bg-ember/10 px-3 py-2 text-ember">
              {getTaskStatusLabel(task.status)}
            </span>
            <span className="rounded-[8px] bg-black/5 px-3 py-2">
              {formatCountLabel(messages.length, "сообщение", "сообщения", "сообщений")}
            </span>
            <span className="rounded-[8px] bg-black/5 px-3 py-2">
              Обновлено {formatDateTime(task.updated_at)}
            </span>
          </div>
        </header>
        {chatSection}
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <header className="glass-panel border border-black/10 p-5 shadow-panel sm:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <p className="section-eyebrow">Рабочее пространство задачи</p>
            <h2 className="mt-3 text-balance text-3xl font-bold text-ink sm:text-4xl">
              {task.title}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate/80">
              Здесь собраны описание задачи, результат ревью, состав команды и чат
              участников.
            </p>
          </div>
          {canAccessChat ? (
            <Link className="ui-button-primary" to={fullChatHref}>
              Открыть полноэкранный чат
            </Link>
          ) : null}
        </div>

        <div className="mt-5 flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate/70">
          <span className="rounded-[8px] bg-ember/10 px-3 py-2 text-ember">
            {getTaskStatusLabel(task.status)}
          </span>
          <span className="rounded-[8px] bg-black/5 px-3 py-2">
            {formatCountLabel(messages.length, "сообщение", "сообщения", "сообщений")}
          </span>
          <span className="rounded-[8px] bg-black/5 px-3 py-2">
            {formatCountLabel(proposals.length, "предложение", "предложения", "предложений")}
          </span>
          <span className="rounded-[8px] bg-black/5 px-3 py-2">
            Обновлено {formatDateTime(task.updated_at)}
          </span>
        </div>
      </header>

      {error ? (
        <p
          aria-live="polite"
          className="rounded-[10px] bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </p>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.95fr)] xl:items-start">
        <div className="space-y-6">
          {chatSection}
        </div>

        <div className="space-y-6">
          <article className="glass-panel border border-black/10 p-5 shadow-panel sm:p-6">
            <p className="section-eyebrow">Описание задачи</p>
            <p className="mt-3 break-words text-sm leading-8 text-slate/80">
              {task.content}
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {task.tags.length === 0 ? (
                <span className="rounded-[8px] border border-dashed border-black/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate/60">
                  Теги не заданы
                </span>
              ) : (
                task.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-[8px] bg-black/5 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate/80"
                  >
                    {tag}
                  </span>
                ))
              )}
            </div>
            <div className="mt-6 grid gap-4">
              <ValidationPanel
                canValidate={canValidate}
                onValidate={handleValidate}
                result={task.validation_result}
                validating={validating}
              />
              <AttachmentUpload
                attachments={task.attachments}
                busy={uploading}
                onUpload={handleUpload}
              />
            </div>
          </article>

          <section className="glass-panel border border-black/10 p-5 shadow-panel sm:p-6">
            <p className="section-eyebrow">Команда задачи</p>
            <div className="mt-4 grid gap-3">
              {teamCards.map((item) => (
                <article
                  key={item.key}
                  className="rounded-[10px] border border-black/10 bg-white/80 p-4"
                >
                  <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate/65">
                    {item.title}
                  </p>
                  {item.member ? (
                    <>
                      <p className="mt-2 font-semibold text-ink">{item.member.full_name}</p>
                      <p className="mt-1 text-sm text-slate/70">
                        {item.member.email} · {getRoleLabel(item.member.role)}
                      </p>
                    </>
                  ) : (
                    <p className="mt-2 text-sm text-slate/70">{item.fallback}</p>
                  )}
                </article>
              ))}
            </div>

            {canApprove ? (
              <div className="mt-5 space-y-4 rounded-[12px] border border-amber-200 bg-amber-50/80 p-4">
                <div>
                  <p className="text-sm font-semibold text-ink">
                    Подтверждение задачи после ревью
                  </p>
                  <p className="mt-1 text-sm text-slate/75">
                    Назначьте одного разработчика и одного тестировщика. После
                    этого задача перейдет в работу команды, а чат откроется для
                    всех участников задачи.
                  </p>
                </div>
                <label className="block">
                  <span className="mb-2 block text-sm font-semibold text-ink/70">
                    Разработчик
                  </span>
                  <select
                    className="ui-field"
                    onChange={(event) => setDeveloperSelection(event.target.value)}
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
                  <span className="mb-2 block text-sm font-semibold text-ink/70">
                    Тестировщик
                  </span>
                  <select
                    className="ui-field"
                    onChange={(event) => setTesterSelection(event.target.value)}
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
                  className="ui-button-primary"
                  disabled={approving || !developerSelection || !testerSelection}
                  onClick={() => void handleApprove()}
                  type="button"
                >
                  {approving ? "Формируем команду..." : "Подтвердить и назначить команду"}
                </button>
              </div>
            ) : null}
          </section>

          <section className="glass-panel border border-black/10 p-5 shadow-panel sm:p-6">
            <TaskForm
              disabled={!canEditTask}
              loading={savingTask}
              onSubmit={handleSave}
              task={task}
            />
          </section>

          <section className="glass-panel border border-black/10 p-5 shadow-panel sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="section-eyebrow">Предложения по изменениям</p>
                <h3 className="mt-2 text-2xl font-bold text-ink">
                  Отслеживаемые изменения требований
                </h3>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {proposals.length === 0 ? (
                <p className="text-sm text-slate/70">
                  Предложений по изменениям пока нет.
                </p>
              ) : (
                proposals.map((proposal) => (
                  <article
                    key={proposal.id}
                    className="rounded-[10px] border border-black/10 bg-white/80 p-4"
                  >
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-ember">
                      {getProposalStatusLabel(proposal.status)}
                    </p>
                    <p className="mt-2 break-words text-sm leading-7 text-slate/80">
                      {proposal.proposal_text}
                    </p>
                    <p className="mt-2 text-xs text-slate/60">
                      Предложил: {proposal.proposed_by_name ?? "неизвестный пользователь"}.
                      {proposal.reviewed_by_name
                        ? ` Рассмотрел: ${proposal.reviewed_by_name}.`
                        : ""}
                    </p>
                    {canReviewProposals && proposal.status === "new" ? (
                      <div className="mt-3 flex flex-wrap gap-3">
                        <button
                          className="ui-button-primary"
                          disabled={reviewingProposalId === proposal.id}
                          onClick={() =>
                            void handleProposalReview(proposal.id, "accepted")
                          }
                          type="button"
                        >
                          Принять
                        </button>
                        <button
                          className="ui-button-secondary"
                          disabled={reviewingProposalId === proposal.id}
                          onClick={() =>
                            void handleProposalReview(proposal.id, "rejected")
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
          </section>
        </div>
      </div>
    </section>
  );
}
