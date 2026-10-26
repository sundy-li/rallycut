export function endReasonLabel(reason?: string): string {
  return (
    (
      {
        out_without_table_bounce: "疑似出界",
        net_drop_same_side: "疑似下网",
        held_after_flight: "疑似接住",
        below_table_stopped: "台下停滞",
        camera_cut: "镜头分界",
        ball_settled: "球路持续放缓",
        activity_gap: "对打活动中断",
        transit_gap: "过台对打中断",
        stroke_gap: "击球中断",
      } as Record<string, string>
    )[reason ?? ""] ?? "终止候选"
  );
}
