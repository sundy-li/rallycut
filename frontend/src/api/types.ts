export interface Video {
  path: string;
  name: string;
  fingerprint: string;
  duration: number;
  width: number;
  height: number;
  fps: number;
  has_audio: boolean;
  codec: string;
  bit_rate: number;
  rotation: number;
}
export interface Rally {
  id: string;
  start: number;
  end: number;
  confidence: number;
  score: number;
  selected: boolean;
  edited: boolean;
  /** Kept for review, but excluded from the actual export timeline. */
  invalid?: boolean;
  /** User-marked highlight, independent of the model score. */
  favorite?: boolean;
  evidence?: "visual" | "visual+audio";
  boundary_before?: boolean;
  start_reason?: string;
  end_reason?: string;
  end_event_time?: number;
  end_confidence?: number;
}
export interface TrackPoint {
  t: number;
  x: number;
  y: number;
  confidence: number;
}
export interface BallTrack {
  id: string;
  points: TrackPoint[];
  /** Far from this video's play area (floor / hall edge): not drawn as the ball. */
  off_play?: boolean;
}
export interface RallyEvent {
  type: "dead_ball" | "restart";
  time: number;
  confirmed_at: number;
  reason: string;
  confidence: number;
  x: number;
  y: number;
  signals: string[];
}
export interface AnalysisStream {
  job_id: string;
  tracks?: BallTrack[];
  table_bounds?: number[] | null;
  processed_seconds?: number;
}

export interface TableSegment {
  start: number;
  end: number;
  bounds?: number[] | null;
  net_region?: number[];
  method?: string;
}

export interface AnalysisSummary {
  method: string;
  decoded_frames: number;
  sampled_frames: number;
  track_count: number;
  elapsed_seconds: number;
  processing_fps?: number;
  analysis_fps?: number;
  table_bounds?: number[] | null;
  table_mode?: "optional" | "off" | "precalibrate";
  geometry_available?: boolean;
  unscored_frames?: number;
  table_segments?: TableSegment[];
  camera_cuts?: number;
  net_region?: number[];
  net_region_source?: string;
  rally_state_version?: string;
  activity_rule_version?: string;
  play_area_version?: string;
  rally_events?: RallyEvent[];
  calibration_method?: string;
  calibration_samples?: number;
  calibration_first_timestamp?: number;
  calibration_last_timestamp?: number;
  calibration_search_seconds?: number;
  calibration_sampled_frames?: number;
  calibration_elapsed_seconds?: number;
  calibration_strategy?:
    | "seek_sparse"
    | "sequential_fallback"
    | "seek_sparse_then_jump"
    | "sequential_fallback_then_jump"
    | "not_required"
    | "search_failed";
  calibration_jump_samples?: number;
  calibration_jump_windows?: number;
  calibration_jump_budget?: number;
  calibration_search_extent_seconds?: number;
  scene_changes: number;
  audio_impacts: number;
  weights_sha256?: string;
  device?: string;
  decoder?: "opencv" | "videotoolbox";
  hardware_decode?: boolean;
  decode_format?: string;
  precision?: "fp32" | "fp16";
  batch_size?: number;
  pipeline?: boolean;
  pipeline_timings?: Record<string, number>;
  implementation?: string;
  detection_frames?: number;
  duplicate_frames?: number;
  warnings: string[];
}
export interface Rules {
  pre_roll: number;
  post_roll: number;
  min_duration: number;
}
export interface ExportSettings {
  codec: "h264" | "hevc";
  encoder: "auto" | "software";
  bit_rate: number;
  /** Human vs machine overlap policy at export time; default "merge". */
  overlap?: OverlapMode;
  /** Burn the player's ball trajectory into the export. */
  show_trajectory?: boolean;
  /** Burn a top-left rally number ("回合 03") into the export. */
  show_rally_labels?: boolean;
}
export type OverlapMode = "merge" | "sequential" | "human" | "machine";
export interface ProcessingPerformance {
  stage: "inference" | "finalizing";
  processed_frames: number;
  elapsed_seconds: number;
  recent_fps: number;
  average_fps: number;
}
export interface Job {
  id: string;
  kind: string;
  status:
    | "running"
    | "cancelling"
    | "completed"
    | "cancelled"
    | "failed"
    | "interrupted";
  progress: number;
  message: string;
  output?: string;
  /** Provisional rallies streamed while an analysis job is still running. */
  candidates?: Rally[];
  processed_seconds?: number;
  performance?: ProcessingPerformance;
  elapsed_seconds?: number;
}
export interface RecentProject {
  path: string;
  name: string;
  video_name: string;
  updated_at: string;
  opened_at: string;
  duration: number;
  rallies: number;
  sources: number;
  analyzed: boolean;
  available: boolean;
  error?: string;
}

export interface Source {
  id: string;
  video: Video;
  sources?: Source[];
  active_source_id?: string;
  rallies: Rally[];
  raw_rallies?: Rally[];
  tracks?: BallTrack[];
  analysis?: AnalysisSummary;
  manual_timeline?: boolean;
  partial_analysis?: boolean;
}

export interface Project {
  schema_version: number;
  id: string;
  name: string;
  video: Video;
  sources?: Source[];
  active_source_id?: string;
  raw_rallies: Rally[];
  rallies: Rally[];
  rules: Rules;
  export_settings: ExportSettings;
  model: string;
  manual_timeline: boolean;
  /** Rallies kept from a cancelled run: usable, but not fully validated. */
  partial_analysis?: boolean;
  analysis_id?: string;
  analysis_runtime?: string;
  tracks?: BallTrack[];
  analysis?: AnalysisSummary;
  updated_at: string;
  job?: Job;
}
export interface SetupState {
  revision?: number;
  state: "checking" | "required" | "running" | "ready" | "failed";
  platform?: string;
  checks?: { id: string; label: string; ready: boolean }[];
  indeterminate?: boolean;
  step: string;
  message: string;
  detail: string;
  progress: number;
  error?: string;
  python?: string;
  needs_network?: boolean;
}

export interface State {
  project: Project | null;
  project_path: string;
  dependencies: Record<string, boolean>;
  error: string;
  setup?: SetupState;
  can_undo?: boolean;
  can_redo?: boolean;
}
