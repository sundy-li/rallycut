import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AlertTriangle,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Keyboard,
  Settings,
  Clapperboard,
  FileVideo,
  FolderOpen,
  HardDrive,
  Import,
  Layers2,
  ListFilter,
  LoaderCircle,
  Merge,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Undo2,
  Redo2,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
  X,
  Volume2,
  VolumeX,
} from "lucide-react";
import {
  api,
  isDesktop,
  subscribeJobs,
  subscribeMenu,
  subscribeSetup,
  subscribeStream,
} from "./api/client";
import type {
  Job,
  OverlapMode,
  Project,
  Rally,
  RecentProject,
  Rules,
  State,
} from "./api/types";
import {
  exportSpans,
  overlapConflicts,
  overlapOptions,
  resolveOverlaps,
  timecode,
} from "./timeline";
import {
  defaultOriginFilter,
  editHiddenByFilter,
  rallyOrigin,
  rallyOriginLabel,
  type RallyOrigin,
} from "./lib/rallies";
import {
  PLAYBACK_RATES,
  SKIP_STEPS,
  loadRallyOnly,
  loadRate,
  loadStep,
  playSpans,
  rallyOnlyTarget,
  rateLabel,
  saveRallyOnly,
  saveRate,
  saveStep,
  skipTarget,
  stepRate,
} from "./playback";
import { describeMediaError } from "./media";
import { endReasonLabel } from "./rally-reasons";
import Court from "./components/Court";
import SeekBar from "./components/SeekBar";
import { HANDLED_KEYS, shortcutKeys, withShortcut } from "./lib/shortcuts";
import RallyTimeEditor from "./components/RallyTimeEditor";
import { defaultExport } from "./components/EncodingOptions";
import SettingsDialog from "./components/SettingsDialog";
import ShortcutsPanel from "./components/ShortcutsPanel";
import ProjectHome from "./components/ProjectHome";
import {
  LiveProcessingStats,
  CompletedProcessingStats,
} from "./components/ProcessingStats";
import { liveOverlay, mergeOverlay } from "./lib/stream";
import { clampedBoundary, markedRange } from "./lib/marks";
import type { OverlayStream } from "./lib/stream";
import { SetupScreen } from "./components/SetupScreen";
import { mergeSetup } from "./lib/setup";
import TrajectoryOverlay, {
  validTableBounds,
} from "./components/TrajectoryOverlay";

const emptyState: State = {
  project: null,
  project_path: "",
  dependencies: {},
  error: "",
};
const defaultRules: Rules = { pre_roll: 0.5, post_roll: 0.8, min_duration: 6 };

// Keys typed into text fields stay there; checkboxes / buttons / sliders do
// not take text, so shortcuts (Space = play / pause) still apply to them.
const NON_TEXT_INPUTS = new Set([
  "checkbox",
  "radio",
  "range",
  "button",
  "submit",
  "reset",
  "color",
  "file",
]);
function isTypingTarget(target: HTMLElement) {
  if (target.isContentEditable) return true;
  if (target.tagName === "TEXTAREA" || target.tagName === "SELECT") return true;
  return (
    target.tagName === "INPUT" &&
    !NON_TEXT_INPUTS.has((target as HTMLInputElement).type)
  );
}

function savedTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return ` ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function defaultProjectName(date = new Date()) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

// Upstream model branding stays out of the product UI, including messages
// restored from older project files.
export const maskModelName = (text: string) =>
  text.replace(/blurball/gi, "视觉模型");

// Friendly names plus the exact command that fixes a missing dependency.
const depHints: Record<string, { label: string; fix: string }> = {
  ffmpeg: { label: "ffmpeg", fix: "brew install ffmpeg" },
  ffprobe: { label: "ffprobe", fix: "brew install ffmpeg" },
  python3: { label: "Python 3", fix: "just setup" },
  opencv_numpy: { label: "OpenCV / NumPy", fix: "just setup" },
  blurball_weights_torch: {
    label: "视觉模型权重与 PyTorch",
    fix: "just setup-model",
  },
};

export default function App() {
  const [state, setState] = useState<State>(emptyState);
  const [job, setJob] = useState<Job>();
  const [view, setView] = useState<"home" | "workspace">("home");
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>([]);
  const [projectListError, setProjectListError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<RecentProject>();
  // Non-null while the "how to resolve overlaps" export dialog is open.
  const [exportOverlap, setExportOverlap] = useState<OverlapMode | null>(null);
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState(() =>
    defaultProjectName(),
  );
  const [renamingProject, setRenamingProject] = useState(false);
  const [projectNameDraft, setProjectNameDraft] = useState("");
  const renameCancelled = useRef(false);
  const [pending, setPending] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "error">(
    "idle",
  );
  const [appConfirm, setAppConfirm] = useState<{
    message: string;
    confirmLabel: string;
  } | null>(null);
  const confirmResolve = useRef<((ok: boolean) => void) | null>(null);
  const [error, setError] = useState("");
  const [help, setHelp] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [focused, setFocused] = useState("");
  const [playhead, setPlayhead] = useState(0);
  const [videoPaused, setVideoPaused] = useState(true);
  const [videoMuted, setVideoMuted] = useState(false);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("time");
  const [originFilter, setOriginFilter] = useState<RallyOrigin | "all">(
    "analysis",
  );
  // Origins before the latest cutting edit; consumed once the result arrives.
  const editOrigins = useRef<Map<string, RallyOrigin> | null>(null);
  const [onlySelected, setOnlySelected] = useState(false);
  const projectID = useRef<string | undefined>(undefined);
  const autoAdoptAttempt = useRef("");
  const [videoError, setVideoError] = useState(false);
  const [videoFailure, setVideoFailure] = useState("");
  const [previewRevision, setPreviewRevision] = useState(0);
  const [showTracks, setShowTracks] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [showRallyCaption, setShowRallyCaption] = useState(false);
  // Preview-only speed / skip step; remembered locally, never exported.
  const [playbackRate, setPlaybackRate] = useState(loadRate);
  const [skipStep, setSkipStep] = useState(loadStep);
  // Skip non-rally gaps while playing (review aid; does not edit anything).
  const [rallyOnly, setRallyOnly] = useState(loadRallyOnly);
  const video = useRef<HTMLVideoElement>(null);
  const previewEnd = useRef<number | null>(null);
  const p = state.project;
  projectID.current = p?.id;
  // While a fresh analysis runs, show provisional rounds as soon as the worker
  // reports them so finished parts of the match can be played immediately.
  const streamingRallies =
    job?.kind === "analysis" &&
    job.status === "running" &&
    (p?.rallies.length ?? 0) === 0 &&
    job.candidates?.length
      ? job.candidates
      : null;
  const streaming = streamingRallies !== null;
  const rallies = streamingRallies ?? p?.rallies ?? [];
  const projectRallies = useRef<Rally[]>([]);
  projectRallies.current = p?.rallies ?? [];
  const rallyCaption = useMemo(() => {
    if (!showRallyCaption || !rallies.length) return "";
    let label = "";
    let latest = -Infinity;
    rallies.forEach((rally, index) => {
      const boundaries: [number, string][] = [
        [rally.start, "开始"],
        [rally.end, "结束"],
      ];
      for (const [time, suffix] of boundaries) {
        if (playhead >= time && playhead <= time + 1.4 && time > latest) {
          latest = time;
          label = `第 ${index + 1} 回合${suffix}`;
        }
      }
    });
    return label;
  }, [rallies, playhead, showRallyCaption]);

  // Optional geometry can arrive independently of tracks; [] explicitly clears
  // the previous shot's box and must not fall back to a saved/stale ROI.
  const [overlayStream, setOverlayStream] = useState<OverlayStream | null>(
    null,
  );
  useEffect(
    () =>
      subscribeStream((update) => {
        setOverlayStream((prev) => mergeOverlay(prev, update));
      }),
    [],
  );
  useEffect(() => {
    setOverlayStream(null);
  }, [job?.id]);
  useEffect(() => {
    if (job?.status !== "running") setOverlayStream(null);
  }, [job?.status]);

  const liveStream = liveOverlay(overlayStream, job);
  const overlayTracks = useMemo(
    () =>
      (liveStream
        ? liveStream.tracks
        : job?.status === "running" && job.kind === "analysis"
          ? []
          : (p?.tracks ?? [])
      ).filter((track) => !track.off_play),
    [liveStream, job?.status, job?.kind, p?.tracks],
  );
  // A broadcast cut can switch the calibrated table box; pick the segment that
  // covers the moment being played back.
  const tableBoundsAt = (time: number) => {
    const segments = p?.analysis?.table_segments;
    if (segments?.length) {
      const segment = segments.find(
        (item) => time >= item.start && time < item.end,
      );
      if (segment) {
        return segment.bounds?.length === 4 ? segment.bounds : undefined;
      }
      return undefined;
    }
    return p?.analysis?.table_bounds;
  };
  const overlayBounds = liveStream
    ? playhead >= (liveStream.tableStart ?? 0)
      ? liveStream.table
      : undefined
    : job?.status === "running" && job.kind === "analysis"
      ? undefined
      : tableBoundsAt(playhead);
  const canShowTracks = overlayTracks.length > 0;
  const canShowTable = validTableBounds(overlayBounds);
  const active = rallies.find((r) => r.id === focused);
  const running = job?.status === "running" || job?.status === "cancelling";
  const analyzing = running && job?.kind === "analysis";
  const disabled = pending || running;
  const selected = rallies.filter((r) => r.selected);
  const duration = p?.video.duration ?? 0;
  const overlapMode: OverlapMode = p?.export_settings?.overlap ?? "merge";
  const clipSpans = useMemo(
    () =>
      p ? exportSpans(rallies, p.rules, p.video.duration, overlapMode) : [],
    [p, rallies, overlapMode],
  );
  const exportDuration = clipSpans.reduce((n, s) => n + s.end - s.start, 0);
  const projectSources = useMemo(() => {
    if (!p) return [];
    const list = p.sources?.length
      ? p.sources
      : [
          {
            id: p.id,
            video: p.video,
            rallies: p.rallies,
            analysis: p.analysis,
          },
        ];
    return list.map((source) =>
      source.id === p.active_source_id
        ? { ...source, rallies, analysis: p.analysis }
        : source,
    );
  }, [p, rallies]);
  const allSelected = projectSources.reduce(
    (total, source) =>
      total +
      resolveOverlaps(source.rallies ?? [], overlapMode).filter(
        (r) => r.selected && !r.invalid,
      ).length,
    0,
  );
  const allConflicts = projectSources.reduce(
    (total, source) => total + overlapConflicts(source.rallies ?? []),
    0,
  );
  const allDuration = projectSources.reduce(
    (total, source) =>
      total +
      (p
        ? exportSpans(
            source.rallies ?? [],
            p.rules,
            source.video.duration,
            overlapMode,
          ).reduce((n, span) => n + span.end - span.start, 0)
        : 0),
    0,
  );

  const [loaded, setLoaded] = useState(false);
  const environmentReady = !isDesktop() || state.setup?.state === "ready";
  const [setupRetrying, setSetupRetrying] = useState(false);
  const retrySetup = async (recheck = false) => {
    if (setupRetrying) return;
    setSetupRetrying(true);
    try {
      setError("");
      if (recheck) {
        const next = await api().RefreshDependencies();
        setState((prev) => ({
          ...next,
          setup: next.setup ? mergeSetup(prev.setup, next.setup) : undefined,
        }));
      } else {
        const next = await api().StartSetup();
        setState((prev) => ({ ...prev, setup: mergeSetup(prev.setup, next) }));
        if (next.state === "ready") await refresh();
      }
    } catch (e) {
      setState((prev) => ({
        ...prev,
        setup: {
          ...prev.setup,
          state: "failed",
          step: prev.setup?.step || "check",
          progress: prev.setup?.progress || 0,
          message: "无法准备环境",
          detail: "",
          error: String(e),
        },
      }));
    } finally {
      setSetupRetrying(false);
    }
  };
  const refresh = useCallback(async () => {
    if (!isDesktop()) {
      setLoaded(true);
      return;
    }
    try {
      const next = await api().GetState();
      setState((prev) => ({
        ...next,
        setup: next.setup ? mergeSetup(prev.setup, next.setup) : undefined,
      }));
      setJob(next.project?.job);
      if (next.error) setError(next.error);
      if (next.setup?.state !== "ready") return;
      let projects: RecentProject[] = [];
      try {
        const recent = await api().ListRecentProjects();
        projects = Array.isArray(recent) ? recent : [];
        setProjectListError("");
      } catch (e) {
        setProjectListError(String(e));
      }
      if (
        next.project &&
        next.project_path &&
        !projects.some((project) => project.path === next.project_path)
      ) {
        projects = [
          {
            path: next.project_path,
            name:
              next.project.name || next.project.video.name || "未命名比赛项目",
            video_name: next.project.video.name,
            updated_at: next.project.updated_at,
            opened_at: next.project.updated_at,
            duration: next.project.video.duration,
            rallies: next.project.rallies.length,
            sources: next.project.sources?.length || 1,
            analyzed: Boolean(next.project.analysis),
            available: true,
          },
          ...projects,
        ];
      }
      setRecentProjects(projects);
    } catch (e) {
      setState((prev) => ({
        ...prev,
        setup: {
          state: "failed",
          step: "check",
          progress: 0,
          message: "无法检查运行环境",
          detail: "",
          error: String(e),
        },
      }));
      throw e;
    } finally {
      setLoaded(true);
    }
  }, []);
  useEffect(
    () =>
      subscribeSetup((next) => {
        setState((prev) => ({ ...prev, setup: mergeSetup(prev.setup, next) }));
        if (next.state === "ready") {
          void refresh().catch((e) => setError(String(e)));
        }
      }),
    [refresh],
  );
  useEffect(() => {
    void refresh().catch((e) => setError(String(e)));
    return subscribeJobs((next) => {
      setJob(next);
      if (!["running", "cancelling"].includes(next.status))
        void refresh().catch((e) => setError(String(e)));
    });
  }, [refresh]);
  useEffect(() => {
    setFocused("");
    setShowTracks(false);
    setShowTable(false);
    setPlayhead(0);
    setVideoError(false);
    setVideoFailure("");
    setPreviewRevision(0);
    previewEnd.current = null;
  }, [p?.id]);
  // Opening a project or switching its source picks the default origin view:
  // machine-detected rallies, or hand-added ones when any exist.
  const originViewKey = p ? `${p.id}:${p.active_source_id ?? ""}` : "";
  useEffect(() => {
    if (!originViewKey) return;
    editOrigins.current = null;
    setOriginFilter(defaultOriginFilter(projectRallies.current));
  }, [originViewKey]);
  useEffect(() => {
    const before = editOrigins.current;
    if (before) {
      editOrigins.current = null;
      if (editHiddenByFilter(before, rallies, originFilter)) {
        setOriginFilter("all");
        return;
      }
    }
    // An emptied "hand-added" view falls back to machine rallies.
    if (
      originFilter === "manual" &&
      !rallies.some((r) => rallyOrigin(r) === "manual")
    )
      setOriginFilter("analysis");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rallies]);
  useEffect(() => {
    if (!video.current) return;
    video.current.defaultPlaybackRate = playbackRate;
    video.current.playbackRate = playbackRate;
  }, [playbackRate, p?.id, p?.active_source_id, previewRevision, videoError]);
  useEffect(() => {
    if (focused && !rallies.some((r) => r.id === focused)) setFocused("");
  }, [rallies, focused]);
  useEffect(() => {
    if (!canShowTable) setShowTable(false);
  }, [canShowTable]);
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (!environmentReady) return;
      if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key === ",") {
        e.preventDefault();
        setShortcutsOpen(false);
        setSettingsOpen(true);
        return;
      }
      if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key === "/") {
        e.preventDefault();
        setSettingsOpen(false);
        setShortcutsOpen(true);
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "o") {
        e.preventDefault();
        if (!disabled && !help) void openProjectFile();
        return;
      }
      if (help) return;
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [help, disabled, refresh, environmentReady]);
  // Native macOS menu items (RallyCut > 设置… ⌘, / 帮助 > 快捷键 ⌘/).
  useEffect(() => {
    const offs = [
      subscribeMenu("settings", () => {
        if (!environmentReady) return;
        setShortcutsOpen(false);
        setSettingsOpen(true);
      }),
      subscribeMenu("shortcuts", () => {
        if (!environmentReady) return;
        setSettingsOpen(false);
        setShortcutsOpen(true);
      }),
      subscribeMenu("help", () => {
        if (environmentReady) setHelp(true);
      }),
    ];
    return () => offs.forEach((off) => off());
  }, [environmentReady]);

  function askConfirmation(
    message: string,
    confirmLabel = "继续",
  ): Promise<boolean> {
    return new Promise((resolve) => {
      if (confirmResolve.current) confirmResolve.current(false);
      confirmResolve.current = resolve;
      setAppConfirm({ message, confirmLabel });
    });
  }
  function closeConfirmation(ok: boolean) {
    const resolve = confirmResolve.current;
    confirmResolve.current = null;
    setAppConfirm(null);
    resolve?.(ok);
  }
  // Returns true on success, false on failure (the error is shown).
  async function run(action: () => Promise<unknown>): Promise<boolean> {
    if (!environmentReady) return false;
    setPending(true);
    setError("");
    try {
      await action();
      await refresh();
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    } finally {
      setPending(false);
    }
  }
  // Cutting edits are written to the project JSON immediately; this only
  // surfaces the write state next to the project name.
  async function save(action: () => Promise<unknown>) {
    editOrigins.current = new Map(rallies.map((r) => [r.id, rallyOrigin(r)]));
    setSaveStatus("saving");
    const ok = await run(action);
    setSaveStatus(ok ? "idle" : "error");
    return ok;
  }
  async function undoEdit() {
    if (!state.can_undo) return;
    await save(() => api().Undo());
  }
  async function redoEdit() {
    if (!state.can_redo) return;
    await save(() => api().Redo());
  }
  useEffect(() => {
    if (
      !environmentReady ||
      !p ||
      p.rallies.length !== 0 ||
      p.raw_rallies.length === 0 ||
      !p.analysis ||
      pending ||
      running
    )
      return;
    const key = `${p.id}:${p.active_source_id ?? ""}:${p.analysis_id ?? ""}:${p.updated_at}`;
    if (autoAdoptAttempt.current === key) return;
    autoAdoptAttempt.current = key;
    void run(() => api().UseAnalysisCandidates());
  }, [p, pending, running, environmentReady]);
  async function update(rs: Rally[], rules = p?.rules ?? defaultRules) {
    await save(() => api().UpdateTimeline(rs, rules));
  }
  async function openProjectFile() {
    let opened = false;
    await run(async () => {
      const result = await api().OpenProject();
      opened = Boolean(result);
    });
    if (opened) setView("workspace");
  }
  function openNewProjectDialog() {
    setPendingDelete(undefined);
    setNewProjectName(defaultProjectName());
    setNewProjectOpen(true);
  }
  async function createProject() {
    const name = newProjectName.trim() || defaultProjectName();
    setNewProjectOpen(false);
    let opened = false;
    await run(async () => {
      const result = await api().CreateProject(name);
      opened = Boolean(result);
    });
    if (opened) setView("workspace");
  }
  function startProjectRename() {
    if (!p || disabled) return;
    setProjectNameDraft(p.name || "");
    setRenamingProject(true);
  }
  async function commitProjectRename() {
    if (renameCancelled.current) {
      renameCancelled.current = false;
      return;
    }
    const name = projectNameDraft.trim();
    setRenamingProject(false);
    if (!p || !name || name === p.name) return;
    await run(() => api().RenameProject(name));
  }
  async function deleteProject(target: RecentProject) {
    setPendingDelete(undefined);
    await run(() => api().DeleteProject(target.path));
  }
  async function openRecentProject(path: string) {
    if (path === state.project_path && state.project) {
      video.current?.pause();
      setView("workspace");
      return;
    }
    let opened = false;
    await run(async () => {
      const result = await api().OpenRecentProject(path);
      opened = Boolean(result);
    });
    if (opened) {
      video.current?.pause();
      setView("workspace");
    }
  }
  function showProjectList() {
    video.current?.pause();
    setView("home");
    void refresh().catch((e) => setError(String(e)));
  }
  async function adoptCandidates() {
    const proceed = await askConfirmation(
      "将用本次机器识别结果替换整个回合列表，人工添加和人工修正的回合都会被移除。可用 ⌘Z 撤销，是否继续？",
      "只用机器结果",
    );
    if (!proceed) return;
    setOriginFilter("analysis");
    await save(() => api().UseAnalysisCandidates());
  }
  function toggleVideoPlayback() {
    const v = video.current;
    if (!v) return;
    if (v.paused) void v.play().catch(() => undefined);
    else v.pause();
  }
  const resumeAfterScrub = useRef(false);
  const [editingTime, setEditingTime] = useState<string | null>(null);
  function saveRallyTime(id: string, start: number, end: number) {
    setEditingTime(null);
    void update(
      rallies.map((item) =>
        item.id === id ? { ...item, start, end, edited: true } : item,
      ),
    );
  }
  function jump(t: number, end: number | null = null) {
    const next = Math.max(0, Math.min(duration, t));
    setPlayhead(next);
    previewEnd.current = end;
    if (video.current) video.current.currentTime = next;
  }
  // Relative skip from the element's real position (React playhead may lag).
  function skip(direction: 1 | -1) {
    const now = video.current?.currentTime ?? playhead;
    jump(skipTarget(now, direction * skipStep, duration));
  }
  function changeRate(rate: number) {
    setPlaybackRate(rate);
    saveRate(rate);
  }
  function changeStep(step: number) {
    setSkipStep(step);
    saveStep(step);
  }
  function toggleRallyOnly() {
    setRallyOnly((on) => {
      saveRallyOnly(!on);
      return !on;
    });
  }
  function focus(r: Rally) {
    setFocused(r.id);
    jump(r.start, r.end);
  }
  function toggleRally(id: string, selected: boolean) {
    void update(
      rallies.map((item) => (item.id === id ? { ...item, selected } : item)),
    );
  }
  function preview() {
    if (!video.current) return;
    if (active) {
      jump(active.start, active.end);
    }
    void video.current.play().catch((error: unknown) => {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setError(
        error instanceof DOMException && error.name === "NotAllowedError"
          ? "播放被系统拦截，请点击视频画面中的原生播放按钮。"
          : `视频播放失败，请重试预览。${error instanceof Error ? error.message : String(error)}`,
      );
    });
  }
  function revealManualRally(r: Rally) {
    editOrigins.current = null;
    setQuery("");
    setOriginFilter("manual");
    setOnlySelected(false);
    setSort("time");
    setFocused(r.id);
  }
  function addRally() {
    if (!p) return;
    const start = Math.min(playhead, Math.max(0, duration - 0.1));
    const r: Rally = {
      id: `manual-${Date.now()}`,
      start,
      end: Math.min(duration, start + 8),
      confidence: 0,
      score: 0,
      selected: true,
      edited: true,
    };
    void update([...rallies, r]).then(() => revealManualRally(r));
  }
  const visible = rallies
    .filter(
      (r, i) =>
        (!onlySelected || r.selected) &&
        (originFilter === "all" || rallyOrigin(r) === originFilter) &&
        (!query ||
          `${i + 1} ${timecode(r.start)} ${timecode(r.end)}`.includes(query)),
    )
    .sort((a, b) =>
      sort === "score"
        ? b.score - a.score
        : sort === "duration"
          ? b.end - b.start - (a.end - a.start)
          : a.start - b.start,
    );
  // Rally-only playback follows the list's current filters, minus voided rows.
  const rallySpans = playSpans(visible.filter((r) => !r.invalid));
  const rallyOnlyActive = rallyOnly && rallySpans.length > 0;
  const depsMissing = Object.entries(state.dependencies)
    .filter(([, ok]) => !ok)
    .map(([name]) => depHints[name] ?? { label: name, fix: "just setup" });
  const depFixes = [...new Set(depsMissing.map((dep) => dep.fix))];
  const analyzed = Boolean(p?.analysis);
  const hasRows = rallies.length > 0;
  const blank = !p
    ? {
        title: "先导入一场比赛",
        hint: "导入原片后即可分析回合，也可以手动添加。",
      }
    : analyzing
      ? {
          title: "正在分析真实视频",
          hint: "进度见下方任务栏；找到的回合会自动出现在这里。",
        }
      : analyzed
        ? {
            title: "这次没有找到可用回合",
            hint: "可以重新分析，或手动添加回合后选择性导出。",
          }
        : {
            title: "还没有回合",
            hint: "点击视频标题右侧的“分析视频”，从原片里找出值得重看的回合；也可以手动添加。",
          };

  const humanRallies = (p?.rallies ?? []).filter(
    (r) => rallyOrigin(r) !== "analysis",
  ).length;
  const analysisDetails = p?.analysis && (
    <details
      className="analysis-summary analysis-details"
      title={`解码 ${p.analysis.decoded_frames.toLocaleString()} 帧 · ${p.analysis.detection_frames ?? 0} 帧检出 · ${p.analysis.track_count} 条轨迹 · ${p.analysis.audio_impacts ?? 0} 个声音瞬态 · ${p.raw_rallies.length} 个原始候选`}
    >
      <summary>
        <ChevronDown size={12} className="analysis-chevron" />
        <span className="analysis-detail-title">分析详情</span>
        <span className="analysis-line">
          {p.analysis.decoded_frames.toLocaleString()} 帧 ·{" "}
          {p.analysis.track_count} 轨迹 ·{" "}
          {p.analysis.elapsed_seconds.toFixed(1)} 秒
          {p.analysis.device && ` · ${p.analysis.device.toUpperCase()}`}
          {p.analysis.precision && ` / ${p.analysis.precision.toUpperCase()}`}
        </span>
      </summary>
      <div className="analysis-detail-body">
        <CompletedProcessingStats summary={p.analysis} />
        <p className="analysis-detail-meta">
          {p.analysis.detection_frames ?? 0} 帧检出 ·{" "}
          {p.analysis.audio_impacts ?? 0} 个声音瞬态 · {p.raw_rallies.length}{" "}
          个原始候选
        </p>
        {p.manual_timeline && p.rallies.length > 0 && (
          <div className="analysis-adopt">
            <span>
              {humanRallies > 0
                ? `已保留 ${humanRallies} 个人工添加/修正的回合，其余机器回合已按本次结果更新。`
                : "已沿用之前取消勾选的机器回合状态。"}
            </span>
            <button
              className="text-button"
              disabled={disabled}
              onClick={adoptCandidates}
            >
              只用机器结果
            </button>
          </div>
        )}
        {p.analysis.warnings.map((warning) => (
          <p className="analysis-warning" key={warning}>
            {maskModelName(warning)}
          </p>
        ))}
      </div>
    </details>
  );

  const recheckDependencies = async () => {
    setPending(true);
    try {
      setState(await api().RefreshDependencies());
    } catch (e) {
      setError(String(e));
    } finally {
      setPending(false);
    }
  };

  const [draggingSource, setDraggingSource] = useState("");
  const [sourceOrder, setSourceOrder] = useState<string[]>([]);
  const sourceListRef = useRef<HTMLDivElement | null>(null);
  const chipPositions = useRef(new Map<string, number>());
  const dragStartOrder = useRef<string[]>([]);
  const dropLanded = useRef(false);
  const sourceKey = projectSources.map((source) => source.id).join("|");
  useEffect(() => {
    setSourceOrder((prev) =>
      prev.join("|") === sourceKey
        ? prev
        : projectSources.map((source) => source.id),
    );
  }, [sourceKey]);
  const orderedSources = useMemo(() => {
    const byID = new Map(projectSources.map((source) => [source.id, source]));
    const ordered = sourceOrder
      .map((id) => byID.get(id))
      .filter((source): source is NonNullable<typeof source> =>
        Boolean(source),
      );
    return ordered.length === projectSources.length ? ordered : projectSources;
  }, [projectSources, sourceOrder]);
  // FLIP: measure chips before the reorder, invert, then let CSS ease them home.
  useLayoutEffect(() => {
    const container = sourceListRef.current;
    if (!container) {
      chipPositions.current.clear();
      return;
    }
    const nodes = Array.from(
      container.querySelectorAll<HTMLElement>("[data-source-id]"),
    );
    for (const node of nodes) {
      const id = node.dataset.sourceId ?? "";
      const left = node.getBoundingClientRect().left;
      const previous = chipPositions.current.get(id);
      chipPositions.current.set(id, left);
      if (previous === undefined || Math.abs(previous - left) < 1) continue;
      node.style.transition = "none";
      node.style.transform = `translateX(${previous - left}px)`;
      void node.offsetWidth;
      node.style.transition = "transform 190ms cubic-bezier(.2,.7,.2,1)";
      node.style.transform = "";
    }
  }, [sourceOrder]);
  const commitSourceOrder = (ids: string[]) => {
    const server = projectSources.map((source) => source.id);
    if (ids.join("|") === server.join("|")) return;
    void reorderSources(ids);
  };
  const dragOverSource = (id: string) => {
    if (!draggingSource || draggingSource === id) return;
    setSourceOrder((order) => {
      const from = order.indexOf(draggingSource);
      const to = order.indexOf(id);
      if (from < 0 || to < 0 || from === to) return order;
      const next = order.slice();
      next.splice(to, 0, next.splice(from, 1)[0]);
      return next;
    });
  };
  const analysisQueue = useRef<string[]>([]);
  const queueRunning = useRef(false);
  const [queueLeft, setQueueLeft] = useState(0);
  const selectSource = async (id: string) => {
    if (!p || id === p.active_source_id) return;
    try {
      const next = await api().SelectSource(id);
      setState((prev) => (prev ? { ...prev, project: next } : prev));
      setPlayhead(0);
      setVideoError(false);
    } catch (e) {
      setError(String(e));
    }
  };
  const [pendingRemove, setPendingRemove] = useState<{
    id: string;
    name: string;
    rallies: number;
  } | null>(null);
  const deleteSource = async (id: string) => {
    try {
      const next = await api().RemoveSource(id);
      setState((prev) => (prev ? { ...prev, project: next } : prev));
      setPlayhead(0);
      setVideoError(false);
    } catch (e) {
      setError(String(e));
    }
  };
  const requestRemove = (
    id: string,
    name: string,
    rallies: number,
    analyzed: boolean,
  ) => {
    if (!p || projectSources.length <= 1) return;
    if (analyzed || rallies > 0) {
      setPendingRemove({ id, name, rallies });
      return;
    }
    void deleteSource(id);
  };
  const reorderSources = async (ids: string[]) => {
    try {
      const next = await api().ReorderSources(ids);
      setState((prev) => (prev ? { ...prev, project: next } : prev));
    } catch (e) {
      setError(String(e));
      void refresh();
    }
  };
  const advanceAnalysis = async () => {
    const id = analysisQueue.current.shift();
    if (!id) {
      queueRunning.current = false;
      setQueueLeft(0);
      return;
    }
    setQueueLeft(analysisQueue.current.length + 1);
    try {
      const project = await api().SelectSource(id);
      setState((prev) => (prev ? { ...prev, project } : prev));
      setJob(await api().StartAnalysis());
    } catch (e) {
      setError(String(e));
      queueRunning.current = false;
      setQueueLeft(0);
    }
  };
  const analyzeSources = () => {
    if (!p) return;
    const ids = projectSources.map((source) => source.id);
    if (ids.length <= 1) {
      void run(() => api().StartAnalysis());
      return;
    }
    analysisQueue.current = ids;
    queueRunning.current = true;
    setQueueLeft(ids.length);
    void advanceAnalysis();
  };
  useEffect(() => {
    if (!queueRunning.current) return;
    if (job && ["running", "cancelling"].includes(job.status)) return;
    if (job?.status === "cancelled" || job?.status === "failed") {
      queueRunning.current = false;
      setQueueLeft(0);
      return;
    }
    const timer = setTimeout(() => void advanceAnalysis(), 350);
    return () => clearTimeout(timer);
  }, [job?.status]);

  const [rallyMenu, setRallyMenu] = useState<{
    id: string;
    x: number;
    y: number;
  } | null>(null);
  const menuRally = rallyMenu
    ? (rallies.find((rally) => rally.id === rallyMenu.id) ?? null)
    : null;
  const toggleInvalidRally = (id: string) => {
    const target = rallies.find((rally) => rally.id === id);
    if (!target) return;
    void update(
      rallies.map((item) =>
        item.id === id
          ? { ...item, invalid: !target.invalid, edited: true }
          : item,
      ),
    );
  };
  const toggleFavoriteRally = (id: string) => {
    const target = rallies.find((rally) => rally.id === id);
    if (!target) return;
    void update(
      rallies.map((item) =>
        item.id === id
          ? { ...item, favorite: !target.favorite, edited: true }
          : item,
      ),
    );
  };
  const deleteRally = (id: string) => {
    void update(rallies.filter((item) => item.id !== id)).then(() =>
      setFocused(""),
    );
  };
  const previewRally = (rally: Rally) => {
    setFocused(rally.id);
    jump(rally.start, rally.end);
  };
  const splitRallyAtPlayhead = (rally: Rally) => {
    if (playhead <= rally.start || playhead >= rally.end) {
      setMarkHint("播放头不在当前回合内，无法拆分");
      return;
    }
    void save(() => api().SplitRally(rally.id, playhead));
    setMarkHint("");
  };
  const mergeSelectedRallies = () => {
    const chosen = rallies.filter((item) => item.selected);
    if (chosen.length < 2) {
      setMarkHint("至少勾选两个相邻回合才能合并");
      return;
    }
    void save(() => api().MergeRallies(chosen.map((item) => item.id)));
    setMarkHint("");
  };

  const [markStart, setMarkStart] = useState<number | null>(null);
  const [markHint, setMarkHint] = useState("");
  const shortcutHandler = useRef<(event: KeyboardEvent) => void>(() => {});
  shortcutHandler.current = (event: KeyboardEvent) => {
    if (!environmentReady) return;
    const target = event.target as HTMLElement | null;
    if (target && isTypingTarget(target)) return;
    // The progress bar owns arrows / Home / End while focused.
    if (
      target?.getAttribute("role") === "slider" &&
      /^(Arrow(Left|Right|Up|Down)|Home|End)$/.test(event.key)
    )
      return;
    if ((event.metaKey || event.ctrlKey) && !event.altKey) {
      const combo = event.key.toLowerCase();
      if (combo === "z" || combo === "y") {
        if (document.querySelector('[role="dialog"]') || disabled || !p) return;
        event.preventDefault();
        if (combo === "y" || event.shiftKey) void redoEdit();
        else void undoEdit();
      }
      return;
    }
    if (event.altKey) return;
    if (document.querySelector('[role="dialog"]')) return;
    if (event.key === "Escape") {
      setMarkStart(null);
      setMarkHint("");
      return;
    }
    // Preview navigation: ←/→ skip by the chosen step, < / > change speed.
    // View-only, so it also works while an analysis is running.
    const navigation: Record<string, () => void> = {
      ArrowLeft: () => skip(-1),
      ArrowRight: () => skip(1),
      "<": () => changeRate(stepRate(playbackRate, -1)),
      ">": () => changeRate(stepRate(playbackRate, 1)),
    };
    const navigate =
      event.shiftKey && event.key.startsWith("Arrow")
        ? undefined
        : navigation[event.key];
    if (navigate && p && !videoError) {
      event.preventDefault();
      navigate();
      return;
    }
    // Play / pause is view-only too: it works while an analysis or export
    // runs, and a focused rally card or checkbox does not swallow it.
    if ((event.key === " " || event.key.toLowerCase() === "k") && p) {
      event.preventDefault();
      if (!event.repeat || event.key !== " ") toggleVideoPlayback();
      return;
    }
    if (disabled || !p) return;
    const key = event.key.toLowerCase();
    const stepRally = (direction: number) => {
      const ordered = [...rallies].sort((a, b) => a.start - b.start);
      if (!ordered.length) return;
      const current = active
        ? ordered.findIndex((item) => item.id === active.id)
        : -1;
      const next =
        current < 0
          ? direction > 0
            ? 0
            : ordered.length - 1
          : Math.max(0, Math.min(ordered.length - 1, current + direction));
      const targetRally = ordered[next];
      setFocused(targetRally.id);
      jump(targetRally.start, targetRally.end);
    };
    if ((HANDLED_KEYS as readonly string[]).includes(key))
      event.preventDefault();
    switch (key) {
      case "i":
        setMarkStart(playhead);
        setMarkHint("");
        break;
      case "o": {
        if (markStart === null) {
          setMarkHint("先按 I 标记回合开始");
          break;
        }
        const range = markedRange(markStart, playhead, duration);
        if (!range) {
          setMarkHint("回合太短或超出视频时长，请重新标记");
          break;
        }
        const rally: Rally = {
          id: `manual-${Date.now()}`,
          start: range.start,
          end: range.end,
          confidence: 0,
          score: 0,
          selected: true,
          edited: true,
        };
        void update([...rallies, rally]).then(() => {
          revealManualRally(rally);
          setMarkStart(null);
          setMarkHint("");
        });
        break;
      }
      case "[":
      case "]": {
        if (!active) {
          setMarkHint("先选中一个回合");
          break;
        }
        const range = clampedBoundary(
          active.start,
          active.end,
          playhead,
          key === "[" ? "start" : "end",
          duration,
        );
        if (!range) {
          setMarkHint("边界无效，请把播放头放在回合另一侧");
          break;
        }
        void update(
          rallies.map((item) =>
            item.id === active.id ? { ...item, ...range, edited: true } : item,
          ),
        );
        setMarkHint("");
        break;
      }
      case "enter":
        if (active) previewRally(active);
        break;
      case "s":
        if (active) splitRallyAtPlayhead(active);
        else setMarkHint("先选中一个回合");
        break;
      case "m":
        mergeSelectedRallies();
        break;
      case "f":
        if (active) toggleFavoriteRally(active.id);
        else setMarkHint("先选中一个回合");
        break;
      case "x":
        if (active) toggleInvalidRally(active.id);
        else setMarkHint("先选中一个回合");
        break;
      case "d":
        if (active) deleteRally(active.id);
        else setMarkHint("先选中一个回合");
        break;
      case "j":
        stepRally(-1);
        break;
      case "l":
        stepRally(1);
        break;
    }
  };
  useEffect(() => {
    const listener = (event: KeyboardEvent) => shortcutHandler.current(event);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
  useEffect(() => {
    setMarkStart(null);
    setMarkHint("");
  }, [p?.id, p?.active_source_id]);
  useEffect(() => {
    if (!rallyMenu) return;
    const close = (event: PointerEvent) => {
      if (!(event.target as HTMLElement).closest(".rally-context-menu"))
        setRallyMenu(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setRallyMenu(null);
    };
    window.addEventListener("pointerdown", close, true);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("pointerdown", close, true);
      window.removeEventListener("keydown", escape);
    };
  }, [rallyMenu]);

  function renderGlobalDialogs() {
    return (
      <>
        {settingsOpen && (
          <SettingsDialog
            hasProject={Boolean(p)}
            disabled={disabled}
            rules={p?.rules ?? defaultRules}
            onRules={(rules) => void update(rallies, rules)}
            exportSettings={p?.export_settings}
            sourceBitRate={p?.video.bit_rate ?? 0}
            onExportSettings={(settings) =>
              void save(() => api().SetExportSettings(settings))
            }
            skipStep={skipStep}
            onSkipStep={changeStep}
            onClose={() => setSettingsOpen(false)}
          />
        )}
        {shortcutsOpen && (
          <ShortcutsPanel onClose={() => setShortcutsOpen(false)} />
        )}
      </>
    );
  }
  function renderConfirmation() {
    if (!appConfirm) return null;
    return (
      <div
        className="modal-backdrop"
        role="presentation"
        onClick={() => closeConfirmation(false)}
      >
        <div
          className="confirm-modal app-confirm-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="app-confirm-title"
          onClick={(event) => event.stopPropagation()}
        >
          <h2 id="app-confirm-title">请确认</h2>
          <p>{appConfirm.message}</p>
          <div className="confirm-actions">
            <button
              className="button ghost"
              onClick={() => closeConfirmation(false)}
            >
              取消
            </button>
            <button
              className="button primary"
              autoFocus
              onClick={() => closeConfirmation(true)}
            >
              {appConfirm.confirmLabel}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const setup = state.setup;
  if (!loaded || !environmentReady) {
    return (
      <SetupScreen
        state={
          setup ?? {
            state: loaded ? "failed" : "checking",
            step: "check",
            message: loaded ? "无法获取环境检测结果" : "正在检查运行环境…",
            detail: "",
            progress: 0,
            error: loaded
              ? "没有收到有效的环境状态，请重新检测或重启应用。"
              : undefined,
          }
        }
        busy={setupRetrying}
        onStart={() => void retrySetup()}
        onRecheck={() => void retrySetup(true)}
      />
    );
  }

  if (view === "home") {
    return (
      <>
        {renderConfirmation()}
        {renderGlobalDialogs()}
        <ProjectHome
          projects={recentProjects}
          currentPath={state.project_path}
          busy={disabled}
          desktop={isDesktop()}
          error={error || projectListError}
          onOpenRecent={(path) => void openRecentProject(path)}
          onOpenFile={() => void openProjectFile()}
          onImport={openNewProjectDialog}
          onRefresh={() => void refresh().catch((e) => setError(String(e)))}
          onDismissError={() => {
            setError("");
            setProjectListError("");
          }}
          onRequestDelete={setPendingDelete}
        />
        {newProjectOpen && (
          <div
            className="modal-backdrop"
            role="presentation"
            onClick={() => setNewProjectOpen(false)}
          >
            <div
              className="confirm-modal new-project-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="new-project-title"
              onClick={(event) => event.stopPropagation()}
            >
              <h2 id="new-project-title">新建项目</h2>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void createProject();
                }}
              >
                <p>先为项目命名，下一步再选择视频素材。</p>
                <label className="project-name-field">
                  项目名称
                  <input
                    aria-label="项目名称"
                    autoFocus
                    maxLength={80}
                    value={newProjectName}
                    onChange={(event) => setNewProjectName(event.target.value)}
                    onFocus={(event) => event.currentTarget.select()}
                  />
                </label>
                <p className="modal-hint">
                  默认使用本地时间，之后可在工作台双击项目名重命名。
                </p>
                <div className="confirm-actions">
                  <button
                    className="button ghost"
                    type="button"
                    onClick={() => setNewProjectOpen(false)}
                  >
                    取消
                  </button>
                  <button className="button primary" type="submit">
                    下一步：选择视频
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
        {pendingDelete && (
          <div
            className="modal-backdrop"
            role="presentation"
            onClick={() => setPendingDelete(undefined)}
          >
            <div
              className="confirm-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="confirm-delete-project-title"
              onClick={(event) => event.stopPropagation()}
            >
              <h2 id="confirm-delete-project-title">删除项目</h2>
              <p>
                将删除项目「{pendingDelete.name || "未命名项目"}
                」的元数据文件，并移出最近项目列表。
                <strong>不会删除项目引用的视频或任何素材文件。</strong>
                此操作无法撤销。
              </p>
              <div className="confirm-actions">
                <button
                  className="button ghost"
                  onClick={() => setPendingDelete(undefined)}
                >
                  取消
                </button>
                <button
                  className="button danger"
                  disabled={disabled}
                  onClick={() => void deleteProject(pendingDelete)}
                >
                  删除项目
                </button>
              </div>
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <a
          className="brand"
          href="#"
          aria-label="返回项目列表"
          title="返回项目列表"
          onClick={(event) => {
            event.preventDefault();
            showProjectList();
          }}
        >
          <span className="brand-mark">
            <span />
            <span />
            <i />
          </span>
          <strong>
            rallycut<span> / </span>
          </strong>
        </a>
        <div className="header-middle">
          <span className="live-dot" />
          {isDesktop() ? "本地工作空间" : "浏览器界面预览"}
          <ChevronRight size={12} />
          {renamingProject && p ? (
            <input
              className="header-project header-project-input"
              aria-label="项目名称"
              autoFocus
              maxLength={80}
              value={projectNameDraft}
              onChange={(event) => setProjectNameDraft(event.target.value)}
              onFocus={(event) => event.currentTarget.select()}
              onBlur={() => void commitProjectRename()}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  event.currentTarget.blur();
                } else if (event.key === "Escape") {
                  event.preventDefault();
                  renameCancelled.current = true;
                  setRenamingProject(false);
                }
              }}
            />
          ) : (
            <span
              className="header-project"
              title={p ? "双击重命名项目" : undefined}
              onDoubleClick={p ? startProjectRename : undefined}
            >
              {p ? p.name || "未命名比赛项目" : "新建项目"}
            </span>
          )}
          {p && (
            <span
              className={`save-status ${saveStatus}`}
              role="status"
              aria-live="polite"
              title="剪辑修改会自动写入项目文件"
            >
              {saveStatus === "saving"
                ? "保存中…"
                : saveStatus === "error"
                  ? "保存失败"
                  : `已自动保存${savedTime(p.updated_at)}`}
            </span>
          )}
        </div>
        <div className="header-actions">
          <button
            className="icon-button"
            disabled={disabled || !state.can_undo}
            aria-label="撤销"
            title={withShortcut("撤销", "undo")}
            onClick={() => void undoEdit()}
          >
            <Undo2 size={15} />
          </button>
          <button
            className="icon-button"
            disabled={disabled || !state.can_redo}
            aria-label="重做"
            title={withShortcut("重做", "redo")}
            onClick={() => void redoEdit()}
          >
            <Redo2 size={15} />
          </button>
          <button
            className="button subtle compact"
            disabled={disabled}
            aria-label="项目列表"
            title="返回项目列表"
            onClick={showProjectList}
          >
            <ArrowLeft size={14} />
            <span className="button-label">项目列表</span>
          </button>
          <button
            className="button subtle compact"
            disabled={disabled}
            aria-label="打开项目"
            title="打开已保存或已分析的 RallyCut 项目（⌘O）"
            onClick={() => void openProjectFile()}
          >
            <FolderOpen size={14} />
            <span className="button-label">打开项目</span>
          </button>
          <button
            className="button ghost compact"
            disabled={disabled || !p}
            aria-label="另存为"
            title="将当前项目另存为…"
            onClick={() => void run(() => api().SaveProjectAs())}
          >
            <Save size={14} />
            <span className="button-label">另存为</span>
          </button>
          <button
            className="button primary compact"
            disabled={disabled}
            aria-label="导入视频"
            onClick={() => void run(() => api().ImportVideos())}
          >
            <Plus size={15} />
            <span className="button-label">导入视频</span>
          </button>
          <span className="header-divider" />
          <span className="offline" title="所有处理都在本机完成">
            <ShieldCheck size={13} />
            完全离线
          </span>
          <button
            className="icon-button"
            title={withShortcut("快捷键", "shortcuts")}
            aria-label="快捷键"
            onClick={() => setShortcutsOpen(true)}
          >
            <Keyboard size={17} />
          </button>
          <button
            className="icon-button"
            title={withShortcut("设置", "settings")}
            aria-label="设置"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings size={16} />
          </button>
          <button
            className="icon-button"
            title="使用说明"
            aria-label="使用说明"
            onClick={() => setHelp(true)}
          >
            <CircleHelp size={17} />
          </button>
        </div>
      </header>

      <nav className="side-rail" aria-label="项目导航">
        <button
          className="rail-button current"
          aria-label="剪辑工作台"
          title="剪辑工作台"
        >
          <Clapperboard size={22} />
        </button>
        <button
          className="rail-button"
          disabled={disabled}
          title="项目列表"
          aria-label="项目列表（侧边栏）"
          onClick={showProjectList}
        >
          <FolderOpen size={21} />
        </button>
        <div className="rail-bottom">
          <button
            className="rail-button"
            title="关于项目"
            aria-label="关于项目"
            onClick={() => setHelp(true)}
          >
            <CircleHelp size={20} />
          </button>
          <span className="rail-avatar">RC</span>
        </div>
      </nav>

      <main className="workspace">
        {!isDesktop() && (
          <div className="notice preview-notice">
            <HardDrive size={15} />
            <span>
              这是界面预览。运行 <code>wails dev</code>{" "}
              启动桌面应用，使用本地导入、分析和导出。
            </span>
          </div>
        )}
        {depsMissing.length > 0 && (
          <div className="notice error compact" role="alert">
            <AlertTriangle size={14} />
            <span>
              缺少 {depsMissing.map((dep) => dep.label).join("、")}（
              <code>{depFixes.join(" / ")}</code>）
            </span>
            <button
              className="text-button"
              disabled={pending}
              onClick={() => void recheckDependencies()}
            >
              {pending ? (
                <LoaderCircle className="spin" size={12} />
              ) : (
                <RefreshCw size={12} />
              )}
              重新检测
            </button>
          </div>
        )}
        {error && (
          <div className="notice error" role="alert">
            <span>{maskModelName(error)}</span>
            <button
              className="icon-button"
              aria-label="关闭错误"
              onClick={() => setError("")}
            >
              <X size={15} />
            </button>
          </div>
        )}

        <div className="studio-grid">
          <div className="main-column">
            <div className="source-bar">
              {p ? (
                <div
                  className="source-list"
                  role="list"
                  ref={sourceListRef}
                  onDragOver={(e) => {
                    e.preventDefault();
                    const list = sourceListRef.current;
                    if (!list) return;
                    const rect = list.getBoundingClientRect();
                    if (e.clientX < rect.left + 36) list.scrollLeft -= 14;
                    else if (e.clientX > rect.right - 36) list.scrollLeft += 14;
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    dropLanded.current = true;
                    commitSourceOrder(sourceOrder);
                    setDraggingSource("");
                  }}
                >
                  {orderedSources.map((source, index) => {
                    const analyzed = Boolean(source.analysis);
                    const busyThis =
                      job?.status === "running" &&
                      source.id === p.active_source_id;
                    const move = (delta: number) => {
                      const ids = orderedSources.map((item) => item.id);
                      const to = index + delta;
                      if (to < 0 || to >= ids.length) return;
                      ids.splice(to, 0, ids.splice(index, 1)[0]);
                      setSourceOrder(ids);
                      commitSourceOrder(ids);
                    };
                    return (
                      <div
                        key={source.id}
                        role="listitem"
                        tabIndex={0}
                        data-source-id={source.id}
                        draggable={!disabled && orderedSources.length > 1}
                        className={`source-chip${source.id === p.active_source_id ? " active" : ""}${draggingSource === source.id ? " dragging" : ""}`}
                        title={`${source.video.name} · ${source.video.width}×${source.video.height} · ${source.video.fps.toFixed(2)}fps · ${timecode(source.video.duration)}`}
                        onClick={() => void selectSource(source.id)}
                        onKeyDown={(e) => {
                          if (e.altKey && e.key === "ArrowLeft") move(-1);
                          if (e.altKey && e.key === "ArrowRight") move(1);
                        }}
                        onDragStart={(e) => {
                          e.dataTransfer.effectAllowed = "move";
                          e.dataTransfer.setData("text/plain", source.id);
                          dragStartOrder.current = sourceOrder;
                          dropLanded.current = false;
                          setDraggingSource(source.id);
                        }}
                        onDragEnd={() => {
                          if (dropLanded.current)
                            commitSourceOrder(sourceOrder);
                          else setSourceOrder(dragStartOrder.current);
                          dropLanded.current = false;
                          setDraggingSource("");
                        }}
                        onDragOver={(e) => {
                          e.preventDefault();
                          dragOverSource(source.id);
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          dropLanded.current = true;
                          commitSourceOrder(sourceOrder);
                          setDraggingSource("");
                        }}
                      >
                        <span className="chip-index">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <span className="chip-text">
                          <strong>{source.video.name}</strong>
                          <span>
                            {timecode(source.video.duration)}
                            {analyzed ? " · 已分析" : " · 未分析"}
                          </span>
                        </span>
                        <span
                          className={`chip-dot${busyThis ? " busy" : analyzed ? " done" : ""}`}
                        />
                        <button
                          type="button"
                          className="chip-remove"
                          title="删除素材"
                          aria-label={`删除素材 ${source.video.name}`}
                          draggable={false}
                          disabled={disabled || orderedSources.length <= 1}
                          onDragStart={(e) => e.stopPropagation()}
                          onClick={(e) => {
                            e.stopPropagation();
                            requestRemove(
                              source.id,
                              source.video.name,
                              (source.rallies ?? []).length,
                              Boolean(source.analysis),
                            );
                          }}
                        >
                          <X size={11} />
                        </button>
                      </div>
                    );
                  })}
                  <button
                    className="source-add"
                    disabled={disabled}
                    title="添加视频（支持多选）"
                    aria-label="添加视频"
                    onClick={() => void run(() => api().ImportVideos())}
                  >
                    <Plus size={15} />
                  </button>
                </div>
              ) : (
                <div className="source-name">
                  <strong>还没有导入比赛视频</strong>
                  <span>MP4、MOV、MKV 等 · 推荐 1080p / 30fps</span>
                </div>
              )}
              <div className="source-actions">
                <button
                  className="button ghost small-button fresh-analysis-button"
                  disabled={disabled || !p}
                  title="重新分析当前素材，不读取缓存；成功后的新结果仍会更新缓存"
                  onClick={() => void run(() => api().StartFreshAnalysis())}
                >
                  无缓存重跑
                </button>
                <button
                  className={`button small-button ${!analyzed ? "primary" : "subtle"}`}
                  disabled={disabled || !p}
                  title={
                    p ? "逐帧分析原片，识别球轨迹与回合候选" : "先导入比赛视频"
                  }
                  onClick={analyzeSources}
                >
                  {analyzing || queueLeft > 0 ? (
                    <LoaderCircle className="spin" size={14} />
                  ) : (
                    <Sparkles size={14} />
                  )}
                  {queueLeft > 0
                    ? `分析中 ${queueLeft}/${projectSources.length}`
                    : analyzing
                      ? "分析中…"
                      : projectSources.length > 1
                        ? `全部分析 (${projectSources.length})`
                        : "分析视频"}
                </button>
                <span className="source-badge">
                  {p ? "本地原片" : "SOURCE"}
                </span>
              </div>
            </div>
            <section
              className={`video-panel ${p ? "has-source" : ""} ${videoError ? "has-video-error" : ""}`}
              aria-label="视频预览"
            >
              {p && !videoError ? (
                <video
                  ref={video}
                  key={`${p.id}:${p.active_source_id ?? ""}:${previewRevision}`}
                  src={`/media/source?project=${encodeURIComponent(p.id)}&v=${encodeURIComponent(p.active_source_id ?? "")}&preview=${previewRevision}`}
                  preload="metadata"
                  playsInline
                  muted={videoMuted}
                  title="点击播放 / 暂停（空格）"
                  onClick={toggleVideoPlayback}
                  onPlay={() => setVideoPaused(false)}
                  onPause={() => setVideoPaused(true)}
                  onEmptied={() => setVideoPaused(true)}
                  onError={(event) => {
                    setVideoFailure(
                      describeMediaError(event.currentTarget.error),
                    );
                    setVideoError(true);
                    previewEnd.current = null;
                  }}
                  onLoadedMetadata={(event) => {
                    event.currentTarget.defaultPlaybackRate = playbackRate;
                    event.currentTarget.playbackRate = playbackRate;
                    if (previewRevision > 0 && playhead > 0)
                      event.currentTarget.currentTime = Math.min(
                        playhead,
                        event.currentTarget.duration,
                      );
                  }}
                  onTimeUpdate={(e) => {
                    const v = e.currentTarget;
                    setPlayhead(v.currentTime);
                    if (rallyOnlyActive) {
                      // Continue across rallies instead of pausing at the
                      // focused rally's end; jump over the gaps between them.
                      previewEnd.current = null;
                      if (v.paused || v.seeking) return;
                      const target = rallyOnlyTarget(v.currentTime, rallySpans);
                      if (target === "stop") v.pause();
                      else if (target) {
                        setFocused(target.id);
                        jump(target.start);
                      }
                      return;
                    }
                    if (
                      previewEnd.current !== null &&
                      v.currentTime >= previewEnd.current
                    ) {
                      v.pause();
                      previewEnd.current = null;
                    }
                  }}
                />
              ) : (
                <>
                  <Court />
                  <div className="empty-video">
                    <div className="eyebrow">
                      YOUR NEXT HIGHLIGHT STARTS HERE
                    </div>
                    <h2>
                      {videoError
                        ? "当前视频无法预览"
                        : "一场比赛，无数个好球。"}
                    </h2>
                    <p>
                      {videoError
                        ? videoFailure ||
                          "视频加载失败，可以重试；原视频不会被修改。"
                        : "导入原片，在本地发现属于你的精彩回合。"}
                    </p>
                    {p && videoError && (
                      <button
                        className="button primary"
                        onClick={() => {
                          setVideoError(false);
                          setVideoFailure("");
                          setPreviewRevision((value) => value + 1);
                        }}
                      >
                        重试预览
                      </button>
                    )}
                    {!p && (
                      <button
                        className="button subtle"
                        disabled={disabled}
                        onClick={() => void run(() => api().ImportVideos())}
                      >
                        <Import size={15} />
                        选择本地视频
                      </button>
                    )}
                    {!p && (
                      <button
                        className="text-button empty-project-link"
                        disabled={disabled}
                        onClick={() => void run(() => api().OpenProject())}
                      >
                        <FolderOpen size={14} />
                        打开已有项目
                      </button>
                    )}
                  </div>
                  <span className="video-corner">
                    RALLYCUT / OFFLINE EDITOR
                  </span>
                </>
              )}
              {p && !videoError && (showTracks || showTable) && (
                <TrajectoryOverlay
                  tracks={overlayTracks}
                  time={playhead}
                  aspect={p.video.width / p.video.height}
                  bounds={overlayBounds}
                  method={p.model}
                  showTracks={showTracks}
                  showTable={showTable}
                />
              )}
              {showRallyCaption && rallyCaption ? (
                <div className="rally-caption" role="status">
                  {rallyCaption}
                </div>
              ) : null}
              {markStart !== null && (
                <div className="mark-status" role="status">
                  开始 {timecode(markStart)} · 按 <kbd>O</kbd> 结束 ·{" "}
                  <kbd>Esc</kbd> 取消
                </div>
              )}
              {markHint && (
                <div className="mark-status hint" role="status">
                  {markHint}
                </div>
              )}
            </section>
            <SeekBar
              duration={duration}
              time={playhead}
              disabled={!p || videoError}
              segments={rallies}
              onSeek={(t) => jump(t)}
              onScrub={(active) => {
                const v = video.current;
                if (!v) return;
                if (active) {
                  resumeAfterScrub.current = !v.paused;
                  v.pause();
                } else if (resumeAfterScrub.current) {
                  resumeAfterScrub.current = false;
                  void v.play().catch(() => undefined);
                }
              }}
            />
            <div className="player-toolbar">
              <div>
                <button
                  className="icon-button"
                  disabled={!p}
                  aria-label={`后退 ${skipStep} 秒`}
                  title={withShortcut(`后退 ${skipStep} 秒`, "skipBack")}
                  onClick={() => skip(-1)}
                >
                  <ArrowLeft size={16} />
                </button>
                <button
                  className="icon-button"
                  disabled={!p || videoError}
                  aria-label={videoPaused ? "播放" : "暂停"}
                  title={withShortcut(videoPaused ? "播放" : "暂停", "play")}
                  onClick={toggleVideoPlayback}
                >
                  {videoPaused ? (
                    <Play size={15} fill="currentColor" />
                  ) : (
                    <Pause size={15} fill="currentColor" />
                  )}
                </button>
                <button
                  className="play-button"
                  disabled={!p || videoError}
                  onClick={preview}
                  aria-label={active ? "重播回合" : "播放原片"}
                  title={
                    active
                      ? rallyOnlyActive
                        ? "从当前回合起点重新播放；已开启“只播回合”，结束后继续播放后续回合，不循环"
                        : "从当前回合起点重新播放，到回合终点暂停，不循环"
                      : "从当前位置播放原视频；选择回合后可从回合起点重播"
                  }
                >
                  {active ? (
                    <RotateCcw size={15} />
                  ) : (
                    <Play size={15} fill="currentColor" />
                  )}
                  <span>{active ? "重播回合" : "播放原片"}</span>
                </button>
                <button
                  className="icon-button"
                  disabled={!p}
                  aria-label={`前进 ${skipStep} 秒`}
                  title={withShortcut(`前进 ${skipStep} 秒`, "skipForward")}
                  onClick={() => skip(1)}
                >
                  <ArrowRight size={16} />
                </button>
                <button
                  className="icon-button"
                  disabled={!p || videoError}
                  aria-label={videoMuted ? "取消静音" : "静音"}
                  aria-pressed={videoMuted}
                  title={videoMuted ? "取消静音" : "静音"}
                  onClick={() => setVideoMuted((value) => !value)}
                >
                  {videoMuted ? <VolumeX size={15} /> : <Volume2 size={15} />}
                </button>
                <label
                  className="player-select"
                  title={`${shortcutKeys("skipBack")} / ${shortcutKeys("skipForward")} 每次跳转的秒数`}
                >
                  <span>步长</span>
                  <select
                    aria-label="跳转步长"
                    value={skipStep}
                    disabled={!p}
                    onChange={(e) => changeStep(Number(e.target.value))}
                  >
                    {SKIP_STEPS.map((step) => (
                      <option key={step} value={step}>
                        {step}s
                      </option>
                    ))}
                  </select>
                </label>
                <label
                  className="player-select"
                  title={`预览倍速（${shortcutKeys("slower")} / ${shortcutKeys("faster")}），只影响预览，不影响导出`}
                >
                  <span>倍速</span>
                  <select
                    aria-label="播放倍速"
                    value={playbackRate}
                    disabled={!p}
                    data-active={playbackRate !== 1 || undefined}
                    onChange={(e) => changeRate(Number(e.target.value))}
                  >
                    {PLAYBACK_RATES.map((rate) => (
                      <option key={rate} value={rate}>
                        {rateLabel(rate)}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="text-button rally-only-toggle"
                  disabled={!p || !rallySpans.length}
                  aria-pressed={rallyOnlyActive}
                  title={
                    rallySpans.length
                      ? "播放时自动跳过回合之间的间隙（按当前列表筛选，跳过作废回合）"
                      : "当前列表没有可播放的回合"
                  }
                  onClick={toggleRallyOnly}
                >
                  只播回合
                </button>
                <span className="timecode">
                  {timecode(playhead)}
                  <span> / {timecode(duration)}</span>
                </span>
              </div>
              <span className="player-tip">
                <span
                  className="overlay-controls"
                  role="group"
                  aria-label="视频叠加显示"
                >
                  <button
                    className="text-button overlay-toggle"
                    data-layer="tracks"
                    disabled={!canShowTracks || videoError}
                    aria-pressed={showTracks}
                    title={
                      canShowTracks
                        ? "独立显示或隐藏候选球轨迹，不改变球桌显示"
                        : job?.status === "running"
                          ? "轨迹会随分析进度逐步出现"
                          : "当前没有可显示的球轨迹"
                    }
                    onClick={() => setShowTracks((value) => !value)}
                  >
                    {showTracks ? "隐藏球轨迹" : "显示球轨迹"}
                  </button>
                  <button
                    className="text-button overlay-toggle"
                    data-layer="table"
                    disabled={!canShowTable || videoError}
                    aria-pressed={showTable}
                    title={
                      canShowTable
                        ? "独立显示或隐藏主球桌范围，不改变球轨迹显示"
                        : job?.status === "running"
                          ? "当前时刻没有可信桌面几何；球检测与轨迹仍会继续"
                          : "当前时刻无可信球桌范围，不影响球轨迹预览"
                    }
                    onClick={() => setShowTable((value) => !value)}
                  >
                    {showTable ? "隐藏球桌" : "显示球桌"}
                  </button>
                  <button
                    className="text-button overlay-toggle"
                    data-layer="rallies"
                    disabled={!rallies.length || videoError}
                    aria-pressed={showRallyCaption}
                    title={
                      rallies.length
                        ? "在播放器中提示回合开始与结束"
                        : "当前没有可显示的回合"
                    }
                    onClick={() => setShowRallyCaption((value) => !value)}
                  >
                    {showRallyCaption ? "隐藏回合" : "显示回合"}
                  </button>
                </span>
                <span className="player-preview-label">
                  {active ? "预览当前回合" : "原视频预览"}
                </span>
                <kbd>SPACE</kbd>
              </span>
            </div>

            <section className="timeline-panel" aria-label="回合时间轴">
              <div className="timeline-labels">
                <span>回合时间轴</span>
                <span>{rallies.length} SEGMENTS</span>
              </div>
              <div
                className="timeline-track"
                onClick={(e) => {
                  if (!p) return;
                  const rect = e.currentTarget.getBoundingClientRect();
                  jump(((e.clientX - rect.left) / rect.width) * duration);
                }}
              >
                {rallies.map((r) => (
                  <button
                    key={r.id}
                    aria-label={`跳转至 ${timecode(r.start)}`}
                    className={`timeline-segment ${r.selected ? "selected" : ""} ${r.id === focused ? "focused" : ""}`}
                    style={{
                      left: `${(r.start / duration) * 100}%`,
                      width: `${((r.end - r.start) / duration) * 100}%`,
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      focus(r);
                    }}
                  />
                ))}
                {!p && (
                  <div className="timeline-empty">导入后，回合将在这里展开</div>
                )}
                <div
                  className="timeline-cursor"
                  style={{
                    left: `${duration ? (playhead / duration) * 100 : 0}%`,
                  }}
                />
              </div>
              <div className="timeline-ticks">
                {[0, 0.25, 0.5, 0.75, 1].map((t) => (
                  <span key={t}>{timecode(duration * t)}</span>
                ))}
              </div>
            </section>
          </div>

          <aside className="side-panel" aria-label="回合面板">
            <div className="side-tabs side-header">
              <h2>
                <Layers2 size={13} />
                回合
                <span className="count">{rallies.length}</span>
              </h2>
            </div>
            <section className="rallies-panel">
              {p?.partial_analysis && (
                <p className="partial-note">
                  <Square size={11} />
                  分析已取消 · 保留已识别的 {rallies.length}{" "}
                  个回合（未完整校验，可继续播放与导出）
                </p>
              )}
              {job?.kind !== "analysis" && analysisDetails}
              {hasRows ? (
                <>
                  {streaming && (
                    <p className="stream-note">
                      <LoaderCircle size={12} className="spin" />
                      已识别 {rallies.length} 个回合，可先播放 · 已分析{" "}
                      {timecode(job?.processed_seconds ?? 0)} /{" "}
                      {timecode(duration)}
                    </p>
                  )}
                  <div className="list-toolbar">
                    <label className="search-box">
                      <Search size={13} />
                      <input
                        aria-label="搜索回合"
                        placeholder="搜索序号 / 时间…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </label>
                    <label
                      className="sort-control origin-control"
                      title="按来源过滤，仅改变显示，不改变导出"
                    >
                      <select
                        aria-label="回合来源"
                        value={originFilter}
                        onChange={(e) =>
                          setOriginFilter(e.target.value as RallyOrigin | "all")
                        }
                      >
                        <option value="all">全部来源</option>
                        <option value="analysis">机器识别</option>
                        <option value="edited">人工修正</option>
                        <option value="manual">手动添加</option>
                      </select>
                      <ChevronDown size={11} />
                    </label>
                    <button
                      className={`icon-button${onlySelected ? " active" : ""}`}
                      title={onlySelected ? "显示全部回合" : "只看已选回合"}
                      aria-label={
                        onlySelected ? "显示全部回合" : "只看已选回合"
                      }
                      aria-pressed={onlySelected}
                      onClick={() => setOnlySelected(!onlySelected)}
                    >
                      <ListFilter size={14} />
                    </button>
                    <label className="sort-control" title="排序">
                      <select
                        aria-label="回合排序"
                        value={sort}
                        onChange={(e) => setSort(e.target.value)}
                      >
                        <option value="time">时间</option>
                        <option value="duration">时长</option>
                        <option value="score">评分</option>
                      </select>
                      <ChevronDown size={11} />
                    </label>
                    <button
                      className="icon-button"
                      title={`添加回合（或在播放时按 ${shortcutKeys("markIn")} 标记开始、${shortcutKeys("markOut")} 标记结束）`}
                      aria-label="添加回合"
                      disabled={disabled || !p}
                      onClick={addRally}
                    >
                      <Plus size={15} />
                    </button>
                  </div>
                  <div className="rallies-list">
                    {visible.map((r) => (
                      <div
                        key={r.id}
                        className={`rally-card${r.id === focused ? " current" : ""}${r.invalid ? " invalid" : ""}${editingTime === r.id ? " editing-time" : ""}`}
                        onClick={(event) => {
                          if (
                            (event.target as HTMLElement).closest(
                              ".rally-time-editor",
                            )
                          )
                            return;
                          focus(r);
                        }}
                        onContextMenu={(event) => {
                          event.preventDefault();
                          setFocused(r.id);
                          setRallyMenu({
                            id: r.id,
                            x: Math.max(
                              8,
                              Math.min(event.clientX, window.innerWidth - 246),
                            ),
                            y: Math.max(
                              8,
                              Math.min(event.clientY, window.innerHeight - 306),
                            ),
                          });
                        }}
                        onKeyDown={(event) => {
                          if (
                            event.key === "ContextMenu" ||
                            (event.shiftKey && event.key === "F10")
                          ) {
                            event.preventDefault();
                            const rect =
                              event.currentTarget.getBoundingClientRect();
                            setFocused(r.id);
                            setRallyMenu({
                              id: r.id,
                              x: Math.min(rect.left, window.innerWidth - 246),
                              y: Math.min(
                                rect.bottom,
                                window.innerHeight - 306,
                              ),
                            });
                          }
                        }}
                        tabIndex={0}
                        role="button"
                      >
                        <input
                          type="checkbox"
                          className="rally-check"
                          aria-label={`保留第 ${rallies.indexOf(r) + 1} 回合`}
                          disabled={disabled}
                          checked={r.selected}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => toggleRally(r.id, e.target.checked)}
                        />
                        <div className="rally-card-main">
                          <div className="rally-card-top">
                            <span className="rally-index">
                              {String(rallies.indexOf(r) + 1).padStart(2, "0")}
                            </span>
                            <span
                              className="rally-range"
                              title={
                                disabled || streaming
                                  ? undefined
                                  : "双击修改起止时间"
                              }
                              onDoubleClick={(event) => {
                                if (disabled || streaming) return;
                                event.stopPropagation();
                                setFocused(r.id);
                                setEditingTime(r.id);
                              }}
                            >
                              {timecode(r.start)}
                              <i>—</i>
                              {timecode(r.end)}
                            </span>
                            <span className="rally-score">
                              {r.score.toFixed(0)}
                            </span>
                          </div>
                          {editingTime === r.id && (
                            <RallyTimeEditor
                              start={r.start}
                              end={r.end}
                              duration={duration}
                              playhead={playhead}
                              onSave={(start, end) =>
                                saveRallyTime(r.id, start, end)
                              }
                              onCancel={() => setEditingTime(null)}
                            />
                          )}
                          <div className="rally-card-sub">
                            <span
                              className={`origin-tag ${rallyOrigin(r)}`}
                              title={
                                rallyOrigin(r) === "manual"
                                  ? "人工创建"
                                  : rallyOrigin(r) === "edited"
                                    ? "分析候选，经人工修正"
                                    : "模型分析候选"
                              }
                            >
                              {rallyOriginLabel(r)}
                            </span>
                            {r.favorite && (
                              <span className="favorite-tag" title="精彩回合">
                                ★
                              </span>
                            )}
                            {r.invalid && (
                              <span className="invalid-tag">无效分</span>
                            )}
                            {r.end_reason && (
                              <span
                                className="rally-end-tag"
                                title={`规则终止证据，需复核 · ${timecode(r.end_event_time ?? r.end, true)}`}
                              >
                                {endReasonLabel(r.end_reason)}
                              </span>
                            )}
                            <span>{(r.end - r.start).toFixed(1)}s</span>
                            <i />
                            <span>
                              {r.evidence === "visual+audio"
                                ? "画面+声音"
                                : "画面"}
                            </span>
                            <i />
                            <span>{Math.round(r.confidence * 100)}%</span>
                            <span className="score-track">
                              <i style={{ width: `${r.score}%` }} />
                            </span>
                            {r.edited && (
                              <span className="edited-dot" title="人工编辑" />
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                    {!visible.length && (
                      <div className="empty-rallies">
                        <Layers2 size={22} />
                        <h3>没有匹配的回合</h3>
                        <p>调整筛选或搜索条件。</p>
                      </div>
                    )}
                  </div>
                  <div className="list-bottom">
                    <label className="select-all">
                      <input
                        type="checkbox"
                        aria-label="全选回合"
                        disabled={disabled || !rallies.length}
                        checked={
                          rallies.length > 0 &&
                          selected.length === rallies.length
                        }
                        onChange={(e) =>
                          void update(
                            rallies.map((r) => ({
                              ...r,
                              selected: e.target.checked,
                            })),
                          )
                        }
                      />
                      已选 <strong>{selected.length}</strong>/{rallies.length}
                    </label>
                    <div>
                      <button
                        className="text-button"
                        title="选中所有不短于阈值的回合"
                        disabled={disabled || !rallies.length}
                        onClick={() =>
                          void update(
                            rallies.map((r) => ({
                              ...r,
                              selected:
                                r.end - r.start >= (p?.rules.min_duration ?? 6),
                            })),
                          )
                        }
                      >
                        <Check size={13} />
                        长回合
                      </button>
                      <button
                        className="text-button"
                        title="把已选回合合并为一个"
                        disabled={disabled || selected.length < 2}
                        onClick={() =>
                          void save(() =>
                            api().MergeRallies(selected.map((r) => r.id)),
                          )
                        }
                      >
                        <Merge size={13} />
                        合并
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="rallies-blank">
                  <Layers2 size={22} />
                  <h3>{blank.title}</h3>
                  <p>{blank.hint}</p>
                </div>
              )}
            </section>
          </aside>
        </div>

        {job && (
          <section className={`job-panel ${job.status}`} aria-live="polite">
            <div className="job-top">
              <span>
                {running ? (
                  <LoaderCircle size={15} className="spin" />
                ) : job.status === "completed" ? (
                  <Check size={15} />
                ) : (
                  <Square size={13} />
                )}
                <strong>
                  {job.kind === "analysis" ? "真实视觉分析" : "MP4 导出"}
                </strong>
                <span>{maskModelName(job.message)}</span>
              </span>
              {running ? (
                <button
                  className="text-button"
                  onClick={() =>
                    void api()
                      .CancelJob()
                      .catch((e) => setError(String(e)))
                  }
                >
                  取消任务
                </button>
              ) : (
                <span className="job-status">
                  {
                    (
                      {
                        completed: "已完成",
                        failed: "失败，可重试",
                        cancelled: "已取消",
                        interrupted: "上次中断",
                      } as Record<string, string>
                    )[job.status]
                  }
                </span>
              )}
            </div>
            <div className="job-progress">
              <i style={{ width: `${job.progress * 100}%` }} />
            </div>
            {job.kind === "analysis" && job.performance && (
              <>
                <LiveProcessingStats
                  stats={job.performance}
                  active={Boolean(running)}
                  elapsed={job.elapsed_seconds}
                />
                <p className="processing-note">
                  画面 FPS
                  不含准备阶段；任务均速包含校验、音轨提取、模型加载和校准
                </p>
              </>
            )}
            {job.kind === "analysis" && !running && analysisDetails}
            {job.output && (
              <div className="output-row">
                <p className="output-path">已保存：{job.output}</p>
                {job.kind === "export" && job.status === "completed" && (
                  <button
                    className="text-button"
                    onClick={() =>
                      void api()
                        .RevealExport()
                        .catch((e) => setError(String(e)))
                    }
                  >
                    <FolderOpen size={14} aria-hidden="true" />
                    打开文件夹
                  </button>
                )}
              </div>
            )}
          </section>
        )}
        {pending && !running && (
          <div className="pending-overlay" role="status">
            <LoaderCircle className="spin" size={20} />
            <span>正在读取或保存本地文件…</span>
          </div>
        )}
        <footer className="export-bar">
          <div className="export-summary">
            <span className="export-icon">
              <Clapperboard size={21} />
            </span>
            <div>
              <strong>
                {allSelected
                  ? `${allSelected} 个回合，值得再看一次。`
                  : "你的下一支集锦，从这里开始。"}
              </strong>
              <span>
                预计时长 <b className="mono">{timecode(allDuration)}</b>
                {projectSources.length > 1 ? (
                  <>
                    <i />
                    {projectSources.length} 个素材
                  </>
                ) : null}
                <i />
                MP4 · {p?.export_settings?.codec === "hevc" ? "HEVC" : "H.264"}
                {p?.video.has_audio ? " + AAC 原片音频" : " · 无音轨"}
                <i />
                {allConflicts > 0 ? (
                  <em className="overlap-chip">
                    {allConflicts} 处人工 / 分析重叠 ·{" "}
                    {overlapOptions.find((o) => o.value === overlapMode)?.label}
                  </em>
                ) : (
                  "缓冲去重 · 死球边界保护"
                )}
              </span>
            </div>
          </div>
          <fieldset
            className="export-overlays"
            disabled={disabled || !p}
            aria-label="导出画面叠加"
          >
            <legend>导出叠加</legend>
            {(
              [
                ["show_trajectory", "球轨迹"],
                ["show_rally_labels", "回合编号"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                <input
                  type="checkbox"
                  checked={Boolean(p?.export_settings?.[key])}
                  onChange={(e) => {
                    const checked = e.target.checked;
                    void save(() =>
                      api().SetExportSettings({
                        ...defaultExport,
                        ...p?.export_settings,
                        [key]: checked,
                      }),
                    );
                  }}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <button
            className="button primary export-button"
            disabled={disabled || !allSelected}
            onClick={() =>
              allConflicts > 0
                ? setExportOverlap(overlapMode)
                : void run(() => api().ExportHighlights())
            }
          >
            <ArrowDownToLine size={17} />
            导出精彩集锦
            <ChevronRight size={15} />
          </button>
        </footer>
      </main>
      {renderConfirmation()}
      {renderGlobalDialogs()}
      {exportOverlap && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setExportOverlap(null)}
        >
          <div
            className="confirm-modal overlap-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="overlap-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="overlap-title">回合有重叠，怎么导出？</h2>
            <p>
              发现 {allConflicts}{" "}
              处人工回合与分析回合重叠。人工与人工、分析与分析之间的重叠会自动合并。
              被覆盖的回合整段不导出，时间轴本身不会改动。
            </p>
            <fieldset className="overlap-options">
              <legend className="sr-only">重叠处理方式</legend>
              {overlapOptions.map((option) => {
                const kept = projectSources.reduce(
                  (n, source) =>
                    n +
                    resolveOverlaps(source.rallies ?? [], option.value).filter(
                      (r) => r.selected && !r.invalid,
                    ).length,
                  0,
                );
                const seconds = p
                  ? projectSources.reduce(
                      (n, source) =>
                        n +
                        exportSpans(
                          source.rallies ?? [],
                          p.rules,
                          source.video.duration,
                          option.value,
                        ).reduce((m, span) => m + span.end - span.start, 0),
                      0,
                    )
                  : 0;
                return (
                  <label
                    key={option.value}
                    className={exportOverlap === option.value ? "checked" : ""}
                  >
                    <input
                      type="radio"
                      name="overlap"
                      value={option.value}
                      checked={exportOverlap === option.value}
                      onChange={() => setExportOverlap(option.value)}
                    />
                    <span>
                      <strong>{option.label}</strong>
                      <small>{option.hint}</small>
                    </span>
                    <span className="overlap-preview mono">
                      {kept} 个 · {timecode(seconds)}
                    </span>
                  </label>
                );
              })}
            </fieldset>
            <div className="confirm-actions">
              <button
                className="button ghost"
                onClick={() => setExportOverlap(null)}
              >
                取消
              </button>
              <button
                className="button primary"
                autoFocus
                onClick={() => {
                  const mode = exportOverlap;
                  setExportOverlap(null);
                  const current = p?.export_settings;
                  void run(async () => {
                    if (mode !== overlapMode)
                      await api().SetExportSettings({
                        codec: current?.codec ?? "h264",
                        encoder: current?.encoder ?? "auto",
                        bit_rate: current?.bit_rate ?? 0,
                        overlap: mode,
                      });
                    await api().ExportHighlights();
                  });
                }}
              >
                按此方式导出
              </button>
            </div>
          </div>
        </div>
      )}
      {pendingRemove && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setPendingRemove(null)}
        >
          <div
            className="confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-remove-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="confirm-remove-title">删除素材</h2>
            <p>
              将删除「{pendingRemove.name}」及其 {pendingRemove.rallies}{" "}
              个回合和分析结果，无法撤销。原视频文件不会被删除。
            </p>
            <div className="confirm-actions">
              <button
                className="button ghost"
                onClick={() => setPendingRemove(null)}
              >
                取消
              </button>
              <button
                className="button danger"
                onClick={() => {
                  const target = pendingRemove;
                  setPendingRemove(null);
                  if (target) void deleteSource(target.id);
                }}
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}

      {rallyMenu && menuRally && (
        <div
          className="rally-context-menu"
          role="menu"
          style={{ left: rallyMenu.x, top: rallyMenu.y }}
          onClick={(event) => event.stopPropagation()}
          onContextMenu={(event) => event.preventDefault()}
        >
          <div className="context-title">
            {rallyOriginLabel(menuRally)} · {timecode(menuRally.start)}—
            {timecode(menuRally.end)}
          </div>
          <button
            role="menuitem"
            onClick={() => {
              previewRally(menuRally);
              setRallyMenu(null);
            }}
          >
            <span>预览 / 定位</span>
            <kbd>Enter</kbd>
          </button>
          <button
            role="menuitem"
            disabled={disabled}
            onClick={() => {
              toggleInvalidRally(menuRally.id);
              setRallyMenu(null);
            }}
          >
            <span>{menuRally.invalid ? "取消无效分" : "标记无效分"}</span>
            <kbd>X</kbd>
          </button>
          <button
            role="menuitem"
            disabled={disabled}
            onClick={() => {
              toggleFavoriteRally(menuRally.id);
              setRallyMenu(null);
            }}
          >
            <span>{menuRally.favorite ? "取消精彩" : "标记精彩"}</span>
            <kbd>F</kbd>
          </button>
          <button
            role="menuitem"
            disabled={
              disabled ||
              playhead <= menuRally.start ||
              playhead >= menuRally.end
            }
            onClick={() => {
              splitRallyAtPlayhead(menuRally);
              setRallyMenu(null);
            }}
          >
            <span>在播放头拆分</span>
            <kbd>S</kbd>
          </button>
          <button
            role="menuitem"
            disabled={disabled || selected.length < 2}
            onClick={() => {
              mergeSelectedRallies();
              setRallyMenu(null);
            }}
          >
            <span>合并已选</span>
            <kbd>M</kbd>
          </button>
          <button
            role="menuitem"
            className="danger"
            disabled={disabled}
            onClick={() => {
              deleteRally(menuRally.id);
              setRallyMenu(null);
            }}
          >
            <span>删除回合</span>
            <kbd>D</kbd>
          </button>
        </div>
      )}

      {help && (
        <div className="modal-backdrop" onClick={() => setHelp(false)}>
          <section
            className="help-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="help-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="icon-button modal-close"
              aria-label="关闭说明"
              onClick={() => setHelp(false)}
            >
              <X size={20} />
            </button>
            <div className="eyebrow">RALLYCUT / FIRST MILESTONE</div>
            <h2 id="help-title">先留下好球，再精进算法。</h2>
            <p>1. 导入本地比赛视频，自动读取元数据并保存项目。</p>
            <p>
              2.
              点击视频标题右侧的“分析视频”，逐帧检测运动小球并关联短轨迹；回合会随分析进度陆续出现，已完成的片段可以立刻回放；在播放器中分别打开“显示球轨迹”“显示球桌”“显示回合”核对，三者独立控制。默认使用本地专用球检测模型。球检测与回合切分是两个环节，后者仍是规则，不承诺未经评估的准确率。
            </p>
            <p>
              3.
              在“回合”面板选择片段预览，点击播放器的“重播回合”可从当前回合起点重新播放，到终点暂停，不自动循环；开启“只播回合”时会继续播放后续回合。双击回合卡片上的时间修改起止点；右键回合卡片可标记无效分
              / 精彩、在播放头拆分或删除；勾选相邻回合可合并。
            </p>
            <p>
              快捷键（<kbd>I</kbd> / <kbd>O</kbd> 标记回合、<kbd>Space</kbd>{" "}
              播放等）都列在快捷键面板里：
              <button
                type="button"
                className="text-button inline-link"
                onClick={() => {
                  setHelp(false);
                  setShortcutsOpen(true);
                }}
              >
                查看全部快捷键（{shortcutKeys("shortcuts")}）
              </button>
              ；片段缓冲与导出编码在设置（{shortcutKeys("settings")}）里。
            </p>
            <p>
              需要强制重新推理时，点击视频标题旁的「无缓存重跑」：只跳过缓存读取，成功后的新结果仍会更新缓存。
            </p>
            <p>
              4. 勾选保留片段，设置前后缓冲，导出 H.264 或 HEVC / AAC MP4；macOS
              优先 VideoToolbox 硬件编码。只选一个回合即可导出单片段。
            </p>
            <p>
              项目包含原视频的绝对路径，不包含视频本身。换机器或移动原片前请备份。新分析只更新原始候选，不覆盖人工编辑。
            </p>
            <div className="notice">
              本机需要 Python 3.12、OpenCV / NumPy、FFmpeg 和 FFprobe。首次运行
              just setup 安装基础依赖，再运行 just setup-model 安装 PyTorch
              和官方权重（仅本地验证）。使用说明、模型许可证核查清单与下一步计划见
              README / docs。
            </div>
            <button
              className="button primary full"
              onClick={() => setHelp(false)}
            >
              开始剪辑
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
