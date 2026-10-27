import type {
  AnalysisStream,
  ExportSettings,
  Job,
  Project,
  Rally,
  RecentProject,
  Rules,
  SetupState,
  State,
} from "./types";

interface Backend {
  GetState(): Promise<State>;
  SetupStatus(): Promise<SetupState>;
  StartSetup(): Promise<SetupState>;
  ImportVideo(): Promise<Project | null>;
  ImportVideos(): Promise<Project | null>;
  CreateProject(name: string): Promise<Project | null>;
  RenameProject(name: string): Promise<Project | null>;
  Undo(): Promise<Project | null>;
  Redo(): Promise<Project | null>;
  SelectSource(id: string): Promise<Project | null>;
  ReorderSources(ids: string[]): Promise<Project | null>;
  RemoveSource(id: string): Promise<Project | null>;
  OpenProject(): Promise<Project | null>;
  OpenRecentProject(path: string): Promise<Project | null>;
  ListRecentProjects(): Promise<RecentProject[]>;
  DeleteProject(path: string): Promise<void>;
  SaveProjectAs(): Promise<string>;
  StartAnalysis(): Promise<Job>;
  /** Rerun inference without reading the cached analysis result. */
  StartFreshAnalysis(): Promise<Job>;
  UseAnalysisCandidates(): Promise<Project>;
  CancelJob(): Promise<void>;
  UpdateTimeline(rallies: Rally[], rules: Rules): Promise<Project>;
  SetExportSettings(settings: ExportSettings): Promise<Project>;
  SplitRally(id: string, at: number): Promise<Project>;
  MergeRallies(ids: string[]): Promise<Project>;
  ExportHighlights(): Promise<Job>;
  /** Select the current project's completed export in Finder / Explorer. */
  RevealExport(): Promise<void>;
  RefreshDependencies(): Promise<State>;
}
declare global {
  interface Window {
    go?: { backend: { App: Backend } };
    runtime?: {
      EventsOn<T>(name: string, cb: (payload: T) => void): () => void;
      /** Quits the desktop app; provided by the Wails runtime. */
      Quit?(): void;
    };
  }
}
export const isDesktop = () => Boolean(window.go?.backend?.App);
export function api(): Backend {
  const backend = window.go?.backend?.App;
  if (!backend)
    throw new Error(
      "当前为浏览器界面预览。请运行 wails dev，在桌面应用中导入本地视频。",
    );
  return backend;
}

export function subscribeSetup(cb: (update: SetupState) => void): () => void {
  return window.runtime?.EventsOn("setup:progress", cb) ?? (() => {});
}

export function subscribeStream(
  cb: (update: AnalysisStream) => void,
): () => void {
  return window.runtime?.EventsOn("analysis:stream", cb) ?? (() => {});
}
export function subscribeJobs(cb: (job: Job) => void): () => void {
  return window.runtime?.EventsOn("job:update", cb) ?? (() => {});
}

/** Native menu items emit "menu:<name>" (see backend/menu.go). */
export function subscribeMenu(
  name: "settings" | "shortcuts" | "help",
  cb: () => void,
): () => void {
  return window.runtime?.EventsOn(`menu:${name}`, cb) ?? (() => {});
}

/**
 * Quit the desktop app.
 *
 * Windows has no native menu bar, so the window chrome plus this in-app button
 * are the only exit affordances there.
 */
export function quitApp(): void {
  window.runtime?.Quit?.();
}
