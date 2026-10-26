import { Component, type ErrorInfo, type ReactNode } from "react";
import "../app-error.css";

interface Props {
  children: ReactNode;
}

interface State {
  error?: Error;
}

export default class AppErrorBoundary extends Component<Props, State> {
  state: State = {};

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("RallyCut UI crashed", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="app-crash" role="alert">
        <span className="eyebrow">RALLYCUT / RECOVERY</span>
        <h1>界面加载失败</h1>
        <p>项目元数据和视频文件没有被修改。可以重新加载界面。</p>
        <code>{this.state.error.message}</code>
        <button
          className="button primary"
          onClick={() => window.location.reload()}
        >
          重新加载
        </button>
      </div>
    );
  }
}
