/**
 * 上传上限：与服务端 apps/server/app/config.py 的 MAX_UPLOAD_BYTES 保持一致（8 MB）。
 * 文案里的数字一律由常量算，不要在页面里写死。
 */
export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

const BYTES_PER_MB = 1024 * 1024;

/** 「8 MB」：给提示文案用 */
export const MAX_UPLOAD_LABEL = `${MAX_UPLOAD_BYTES / BYTES_PER_MB} MB`;

/** 文件体积：「9.2 MB」「820 KB」 */
export function formatFileSize(bytes: number): string {
  if (bytes < BYTES_PER_MB) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  const mb = Math.round((bytes / BYTES_PER_MB) * 10) / 10;
  return `${mb} MB`;
}

/** 超限时的行内错误：「图片 9.2 MB，超过 8 MB，请压缩后重试」；未超限返回 null */
export function uploadSizeError(file: { size: number }): string | null {
  if (file.size <= MAX_UPLOAD_BYTES) return null;
  return `图片 ${formatFileSize(file.size)}，超过 ${MAX_UPLOAD_LABEL}，请压缩后重试`;
}
