import {
  AlertTriangle,
  ArrowRight,
  Clock3,
  FileVideo,
  FolderOpen,
  HardDrive,
  Layers2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import type { RecentProject } from "../api/types";
import "../project-home.css";

interface ProjectHomeProps {
  projects: RecentProject[];
  currentPath: string;
  busy: boolean;
  desktop: boolean;
  error: string;
  onOpenRecent: (path: string) => void;
  onOpenFile: () => void;
  onImport: () => void;
  onRefresh: () => void;
  onDismissError: () => void;
  onRequestDelete: (project: RecentProject) => void;
}

function durationLabel(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  if (hours > 0)
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function openedLabel(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function folderLabel(path: string) {
  const parts = path.replace(/\\/g, "/").split("/");
  parts.pop();
  return parts.join("/") || path;
}

export default function ProjectHome({
  projects,
  currentPath,
  busy,
  desktop,
  error,
  onOpenRecent,
  onOpenFile,
  onImport,
  onRefresh,
  onDismissError,
  onRequestDelete,
}: ProjectHomeProps) {
  const rows = Array.isArray(projects) ? projects : [];
  return (
    <div className="project-home">
      <header className="project-home-header">
        <div className="brand project-home-brand" aria-label="RallyCut">
          <span className="brand-mark">
            <span />
            <span />
            <i />
          </span>
          <strong>
            rallycut<span> / </span>
          </strong>
        </div>
        <span className="project-home-local">
          <ShieldCheck size={15} />
          本地项目库
        </span>
      </header>

      <main className="project-home-main">
        <section className="project-home-intro">
          <span className="eyebrow">YOUR LOCAL MATCH LIBRARY</span>
          <h1>从哪一场比赛开始？</h1>
          <p>
            继续之前的工作，或打开一个 RallyCut
            项目文件。项目、原片和识别结果只保存在这台电脑上。
          </p>
          <div className="project-home-actions">
            <button
              className="button primary"
              disabled={busy}
              onClick={onImport}
            >
              <Plus size={16} />
              新建项目
            </button>
            <button
              className="button subtle"
              disabled={busy}
              onClick={onOpenFile}
            >
              <FolderOpen size={16} />
              打开项目文件
            </button>
          </div>
          {!desktop && (
            <div className="project-home-preview">
              <HardDrive size={15} />
              当前是浏览器界面预览。请运行 <code>wails dev</code>{" "}
              使用本地项目列表和文件选择器。
            </div>
          )}
        </section>

        <section className="project-library" aria-labelledby="recent-title">
          <div className="project-library-heading">
            <div>
              <span className="eyebrow">RECENT</span>
              <h2 id="recent-title">之前打开的项目</h2>
            </div>
            <button
              className="icon-button"
              aria-label="刷新项目列表"
              title="刷新项目列表"
              disabled={busy}
              onClick={onRefresh}
            >
              <RefreshCw size={15} />
            </button>
          </div>

          {error && (
            <div className="project-home-error" role="alert">
              <AlertTriangle size={15} />
              <span>{error}</span>
              <button className="text-button" onClick={onDismissError}>
                关闭
              </button>
            </div>
          )}

          {rows.length === 0 ? (
            <div className="project-library-empty">
              <FileVideo size={28} />
              <h3>还没有最近项目</h3>
              <p>新建一个项目，或打开已有的 *-rallycut.json 项目。</p>
            </div>
          ) : (
            <div className="project-list">
              {rows.map((project) => {
                const current = project.path === currentPath;
                const duration = durationLabel(project.duration);
                return (
                  <div
                    className={`project-card${current ? " current" : ""}${project.available ? "" : " unavailable"}`}
                    key={project.path}
                  >
                    <button
                      className="project-card-open"
                      disabled={busy || !project.available}
                      aria-current={current ? "page" : undefined}
                      title={project.error || project.path}
                      onClick={() => onOpenRecent(project.path)}
                    >
                      <span className="project-card-icon" aria-hidden="true">
                        <FileVideo size={19} />
                      </span>
                      <span className="project-card-body">
                        <span className="project-card-title">
                          {project.name || "未命名比赛项目"}
                          {current && <em>当前</em>}
                        </span>
                        <span className="project-card-video">
                          {project.video_name}
                        </span>
                        <span className="project-card-meta">
                          {duration && (
                            <span>
                              <Clock3 size={11} />
                              {duration}
                            </span>
                          )}
                          <span>
                            <Layers2 size={11} />
                            {project.analyzed
                              ? `${project.rallies} 个回合`
                              : "尚未分析"}
                          </span>
                          {project.sources > 1 && (
                            <span>{project.sources} 段素材</span>
                          )}
                          {openedLabel(project.opened_at) && (
                            <span>{openedLabel(project.opened_at)}</span>
                          )}
                        </span>
                        <span className="project-card-path">
                          {project.available
                            ? folderLabel(project.path)
                            : project.error || "项目文件不可用"}
                        </span>
                      </span>
                      <span className="project-card-action">
                        {project.available
                          ? current
                            ? "继续"
                            : "打开"
                          : "不可用"}
                        {project.available && <ArrowRight size={14} />}
                      </span>
                    </button>
                    <button
                      className="project-card-delete"
                      disabled={busy}
                      aria-label={`删除项目 ${project.name || project.path}`}
                      title="删除项目元数据（不会删除视频文件）"
                      onClick={() => onRequestDelete(project)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>

      <footer className="project-home-footer">
        <span>
          <HardDrive size={13} />
          本地存储
        </span>
        <span>RallyCut / Offline Editor</span>
      </footer>
    </div>
  );
}
