export const ALLOWED_UPLOAD_EXTENSIONS = [
  'pdf', 'txt', 'docx', 'html', 'htm', 'png', 'jpg', 'jpeg', 'webp', 'heic',
];
export const MAX_FILES = 5;
export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_AGGREGATE_BYTES = 25 * 1024 * 1024;
export const MAX_TEXT_LENGTH = 100_000;

export function validateFiles(selected: File[]): string | null {
  if (selected.length === 0) return null;
  if (selected.length > MAX_FILES) {
    return `You can upload up to ${MAX_FILES} files at a time (selected ${selected.length}).`;
  }
  const invalidExt = selected.filter(f => {
    const ext = f.name.split('.').pop()?.toLowerCase() ?? '';
    return !ALLOWED_UPLOAD_EXTENSIONS.includes(ext);
  });
  if (invalidExt.length > 0) {
    return `Unsupported file type: ${invalidExt.map(f => f.name).join(', ')}. ` +
      'Use PDF, TXT, DOCX, HTML, or an image (PNG/JPG/WEBP/HEIC).';
  }
  const tooLarge = selected.filter(f => f.size > MAX_FILE_BYTES);
  if (tooLarge.length > 0) {
    return `File too large (max 10MB each): ${tooLarge.map(f => f.name).join(', ')}.`;
  }
  const totalBytes = selected.reduce((sum, f) => sum + f.size, 0);
  if (totalBytes > MAX_AGGREGATE_BYTES) {
    return 'Combined file size is too large (max 25MB total). Remove a file and try again.';
  }
  return null;
}

export function validateText(text: string): string | null {
  if (text.length > MAX_TEXT_LENGTH) {
    return `Pasted text is too long (max ${MAX_TEXT_LENGTH.toLocaleString()} characters, ` +
      `got ${text.length.toLocaleString()}). Try shortening it or uploading a file instead.`;
  }
  return null;
}
