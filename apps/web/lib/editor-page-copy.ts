// Plain text only: never persist executable HTML, signed URLs, or form secrets.
export function editorPageCopy(root: HTMLElement): string {
  function read(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent || "";
    if (!(node instanceof HTMLElement)) return "";
    if (node.matches('script,style,button,nav,[role="alert"],[role="status"],[data-editor-copy-exclude],dialog:not([open])') || node.hidden || node.getAttribute('aria-hidden') === 'true') return "";
    if (node instanceof HTMLTextAreaElement) return `\n${node.value}\n`;
    if (node instanceof HTMLSelectElement) return Array.from(node.selectedOptions).map(o=>o.textContent).join(', ');
    if (node instanceof HTMLInputElement) {
      if (['password','hidden','file'].includes(node.type)) return "";
      if (['checkbox','radio'].includes(node.type)) return node.checked ? '[selected] ' : '[not selected] ';
      return node.value;
    }
    if (node instanceof HTMLImageElement) return node.alt ? `\n[Image: ${node.alt}]\n` : '';
    if (node.matches('video,audio')) return '\n[Media preview — see original project materials]\n';
    const text=Array.from(node.childNodes).map(read).join('');
    if (/^H[1-6]$/.test(node.tagName)) return `\n\n${'#'.repeat(Number(node.tagName[1]))} ${text.trim()}\n`;
    if (node.tagName==='BR') return '\n';
    return node.matches('p,div,section,article,li,label,pre,fieldset,summary,tr') ? `\n${text.trim()}\n` : text;
  }
  return read(root).replace(/\n[ \t]*\n[ \t]*\n/g,'\n\n').trim();
}
