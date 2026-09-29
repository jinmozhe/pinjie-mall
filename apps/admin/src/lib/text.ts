/**
 * 文本处理工具函数
 *
 * 用于将富文本编辑器输出的 HTML 字符串在列表场景下转为纯文本展示。
 */

/**
 * 去除字符串中的所有 HTML 标签，返回纯文本。
 * 同时将 HTML 实体（&amp;、&lt; 等）还原为可读字符。
 *
 * @example
 * stripHtml('<p><b>品界</b>甄选</p>') // => '品界甄选'
 */
export function stripHtml(html: string): string {
  if (!html) return "";
  // 将常见块级标签替换为换行，保留段落之间的语义间隔
  const withBreaks = html
    .replace(/<\/(p|div|li|br|h[1-6])[^>]*>/gi, " ")
    .replace(/<br\s*\/?>/gi, " ");
  // 去除剩余所有标签
  const plain = withBreaks.replace(/<[^>]+>/g, "");
  // 还原 HTML 实体
  return plain
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * 截取文本到指定长度，超出时追加省略号。
 * 默认截取前 150 个字符。
 *
 * @example
 * truncateText('一段很长的文字...', 20) // => '一段很长的文字...（截取后）…'
 */
export function truncateText(text: string, maxLength = 150): string {
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "…";
}

/**
 * 组合函数：去除 HTML 标签后截取前 N 个字符。
 * 列表场景下的统一入口。
 *
 * @example
 * plainTextPreview('<p><b>品界</b>甄选精品</p>', 10)
 */
export function plainTextPreview(html: string, maxLength = 150): string {
  return truncateText(stripHtml(html), maxLength);
}
