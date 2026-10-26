export function describeMediaError(
  error: Pick<MediaError, "code" | "message"> | null,
): string {
  const code = error?.code ?? 0;
  const reason: Record<number, string> = {
    1: "视频加载被中止，可重试预览。",
    2: "本地视频读取失败，请检查原片是否存在或重试。",
    3: "视频解码失败，请检查文件完整性和系统解码支持。",
    4: "媒体响应或格式不可用；可能未返回视频数据，不一定是编码问题。",
  };
  const detail = error?.message?.trim().slice(0, 240);
  return `${reason[code] ?? "视频加载失败，请重试预览。"}（错误码 ${code}${detail ? `：${detail}` : ""}）`;
}
