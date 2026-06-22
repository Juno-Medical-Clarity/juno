export function renderMarkdown(md: string): string {
  const lines = md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/^- (.+)$/gm, '<li>$1</li>');

  // Wrap contiguous <li> runs in <ul>
  const withLists = lines.replace(/(<li>[\s\S]*?<\/li>)(\n<li>[\s\S]*?<\/li>)*/g, match => `<ul>${match}</ul>`);

  // Wrap non-tag blocks in <p>
  return withLists
    .split(/\n{2,}/)
    .map(block => block.trim())
    .filter(Boolean)
    .map(block => (block.startsWith('<') ? block : `<p>${block}</p>`))
    .join('\n');
}
