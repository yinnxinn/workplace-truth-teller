// inject_body.js - Inject article HTML content into WeChat MP ProseMirror editor
// Historical DOM-only helper. Use only when the host permits page mutations.
// Inspect the active editor and replace the payload first. Never run as-is.
// Prefer the host's rich-text paste/editor API. success != persisted draft.
//
// IMPORTANT: The HTML_CONTENT variable below must be replaced with the actual article HTML
// before execution. This script serves as a template — the agent should replace the 
// htmlContent string with the real article body HTML.
//
// The HTML should be inline-styled (no external CSS), using <section> or <div> for structure,
// compatible with WeChat's rich text rendering.

(function() {
    // =============================================
    // ⚠️  REPLACE THIS STRING WITH ACTUAL ARTICLE HTML
    // =============================================
    var htmlContent = [
        '<p><strong>请替换此内容为实际文章正文HTML</strong></p>',
        '<p>使用 find_editor.js 确认编辑器类型后，将文章HTML填入此处。</p>'
    ].join('');

    var editor = document.querySelector('.ProseMirror');

    if (!editor) {
        // Fallback: try other editor types
        editor = document.querySelector('#ueditor_0') ||
                 document.querySelector('.edui-body-container') ||
                 document.querySelector('[contenteditable="true"][class*="body"]');
    }

    if (editor) {
        // Focus editor first
        editor.focus();
        
        // Small delay to ensure focus is set (synchronous, but helps some editors)
        
        // Set content via innerHTML
        editor.innerHTML = htmlContent;
        
        // Trigger input event so ProseMirror/React detects the change
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        editor.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Return confirmation with character count
        return JSON.stringify({
            success: true,
            editorType: editor.className ? editor.className.substring(0, 40) : 'unknown',
            contentLength: htmlContent.length,
            textLength: editor.textContent.length,
            message: 'Content injected successfully'
        });
    } else {
        return JSON.stringify({
            success: false,
            message: 'Editor element not found. Run find_editor.js first to detect editor type.',
            hint: 'Run scripts/find_editor.js through the active browser controller before retrying.'
        });
    }
})();
