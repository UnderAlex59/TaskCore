import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  public constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  public static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center px-6">
          <div className="glass-panel max-w-lg rounded-[28px] border border-black/10 p-10 shadow-panel">
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-ember">Ошибка интерфейса</p>
            <h1 className="mt-3 text-3xl font-extrabold text-ink">Интерфейс столкнулся с непредвиденным состоянием.</h1>
            <p className="mt-4 text-sm leading-7 text-ink/70">
              Перезагрузите страницу. Если проблема повторится, проверьте
              консоль браузера и логи backend перед дальнейшими изменениями.
            </p>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
