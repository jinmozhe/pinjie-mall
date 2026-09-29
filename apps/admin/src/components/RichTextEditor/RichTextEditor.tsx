/**
 * RichTextEditor —— 基于 Tiptap 的轻量富文本编辑器
 *
 * 功能：加粗、斜体、下划线、有序/无序列表、字体颜色、清除格式
 * 输出：HTML 字符串（与 Ant Design Form 受控模式兼容）
 * 小程序端：存储的 HTML 字符串可直接通过 mp-html 组件渲染
 */
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import { Color } from "@tiptap/extension-color";
import { TextStyle } from "@tiptap/extension-text-style";
import Placeholder from "@tiptap/extension-placeholder";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { theme } from "antd";
import {
  BoldOutlined,
  ItalicOutlined,
  UnderlineOutlined,
  OrderedListOutlined,
  UnorderedListOutlined,
  ClearOutlined,
} from "@ant-design/icons";
import "./RichTextEditor.css";

/** 颜色预设列表（空字符串表示恢复默认色） */
const COLOR_PRESETS = [
  // 第一行：暖色系
  { label: "深红", value: "#c92a2a" },
  { label: "红色", value: "#e03131" },
  { label: "橙红", value: "#e8590c" },
  { label: "橙色", value: "#e67700" },
  { label: "黄色", value: "#e9b824" },
  { label: "金色", value: "#c49a00" },
  // 第二行：冷色系
  { label: "深绿", value: "#1e7e34" },
  { label: "绿色", value: "#2f9e44" },
  { label: "青色", value: "#0c8599" },
  { label: "深蓝", value: "#1864ab" },
  { label: "蓝色", value: "#1971c2" },
  { label: "紫色", value: "#7048e8" },
  // 第三行：中性色
  { label: "黑色", value: "#212529" },
  { label: "深灰", value: "#495057" },
  { label: "灰色", value: "#868e96" },
  { label: "浅灰", value: "#adb5bd" },
  { label: "默认", value: "" },
];

interface RichTextEditorProps {
  /** 当前 HTML 值（Ant Design Form value 注入） */
  value?: string;
  /** 值变化回调（Ant Design Form onChange 注入） */
  onChange?: (html: string) => void;
  /** 占位文字 */
  placeholder?: string;
  /** 最小高度（px），默认 120 */
  minHeight?: number;
  /** 是否禁用 */
  disabled?: boolean;
}

export function RichTextEditor({
  value,
  onChange,
  placeholder = "请输入内容（选填）",
  minHeight = 120,
  disabled = false,
}: RichTextEditorProps) {
  const { token } = theme.useToken();
  // 防止 onChange 触发时再回写导致死循环
  const isInternalChange = useRef(false);
  // 颜色面板开关
  const [colorOpen, setColorOpen] = useState(false);
  /* eslint-disable no-undef */
  const colorPanelRef = useRef<HTMLDivElement>(null);

  // 点击面板外部时关闭
  const handleColorOutsideClick = useCallback((e: MouseEvent) => {
    if (colorPanelRef.current && !colorPanelRef.current.contains(e.target as Node)) {
      setColorOpen(false);
    }
  }, []);
  /* eslint-enable no-undef */

  useEffect(() => {
    if (colorOpen) {
      document.addEventListener("mousedown", handleColorOutsideClick);
    } else {
      document.removeEventListener("mousedown", handleColorOutsideClick);
    }
    return () => { document.removeEventListener("mousedown", handleColorOutsideClick); };
  }, [colorOpen, handleColorOutsideClick]);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        // 禁用代码块，减少不必要功能
        code: false,
        codeBlock: false,
        blockquote: false,
        horizontalRule: false,
        strike: false,
      }),
      Underline,
      TextStyle,
      Color,
      Placeholder.configure({ placeholder }),
    ],
    content: value || "",
    editable: !disabled,
    onUpdate: ({ editor }) => {
      isInternalChange.current = true;
      // 纯空白时返回空字符串，避免后端存入 <p></p>
      const html = editor.isEmpty ? "" : editor.getHTML();
      onChange?.(html);
    },
  });

  // 外部 value 变化时同步内容（Form reset / 初始填充编辑态）
  useEffect(() => {
    if (!editor) return;
    if (isInternalChange.current) {
      isInternalChange.current = false;
      return;
    }
    const incoming = value || "";
    const current = editor.isEmpty ? "" : editor.getHTML();
    if (incoming !== current) {
      editor.commands.setContent(incoming, { emitUpdate: false });
    }
  }, [value, editor]);

  // disabled 状态同步
  useEffect(() => {
    editor?.setEditable(!disabled);
  }, [disabled, editor]);

  if (!editor) return null;

  const toolbarBtn = (
    active: boolean,
    onClick: () => void,
    icon: ReactNode,
    title: string,
  ) => (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`rte-toolbar-btn${active ? " rte-toolbar-btn--active" : ""}`}
    >
      {icon}
    </button>
  );

  return (
    <div
      className="rte-wrapper"
      style={
        {
          "--rte-border": token.colorBorder,
          "--rte-border-focus": token.colorPrimaryBorder,
          "--rte-radius": token.borderRadius + "px",
          "--rte-bg": token.colorBgContainer,
          "--rte-text": token.colorText,
          "--rte-toolbar-bg": token.colorFillAlter,
          "--rte-min-height": minHeight + "px",
          "--rte-disabled-bg": token.colorBgContainerDisabled,
          "--rte-placeholder": token.colorTextPlaceholder,
        } as CSSProperties
      }
    >
      {/* 工具栏 */}
      <div className="rte-toolbar">
        {toolbarBtn(
          editor.isActive("bold"),
          () => editor.chain().focus().toggleBold().run(),
          <BoldOutlined />,
          "加粗",
        )}
        {toolbarBtn(
          editor.isActive("italic"),
          () => editor.chain().focus().toggleItalic().run(),
          <ItalicOutlined />,
          "斜体",
        )}
        {toolbarBtn(
          editor.isActive("underline"),
          () => editor.chain().focus().toggleUnderline().run(),
          <UnderlineOutlined />,
          "下划线",
        )}

        <span className="rte-toolbar-divider" />

        {toolbarBtn(
          editor.isActive("bulletList"),
          () => editor.chain().focus().toggleBulletList().run(),
          <UnorderedListOutlined />,
          "无序列表",
        )}
        {toolbarBtn(
          editor.isActive("orderedList"),
          () => editor.chain().focus().toggleOrderedList().run(),
          <OrderedListOutlined />,
          "有序列表",
        )}

        <span className="rte-toolbar-divider" />

        {/* 颜色选择器 —— 色块面板 */}
        <div ref={colorPanelRef} className="rte-color-picker-wrap">
          <button
            type="button"
            title="文字颜色"
            className="rte-toolbar-btn rte-color-trigger"
            onClick={() => setColorOpen((v) => !v)}
          >
            {/* 字母 A + 当前颜色下划线 */}
            <span className="rte-color-icon">
              <span className="rte-color-icon-a">A</span>
              <span
                className="rte-color-icon-bar"
                style={{ background: editor.getAttributes("textStyle").color || token.colorText }}
              />
            </span>
          </button>

          {colorOpen && (
            <div className="rte-color-panel">
              <div className="rte-color-grid">
                {COLOR_PRESETS.map((c) =>
                  c.value ? (
                    <button
                      key={c.value}
                      type="button"
                      title={c.label}
                      className={`rte-color-swatch${editor.getAttributes("textStyle").color === c.value ? " rte-color-swatch--active" : ""}`}
                      style={{ background: c.value }}
                      onClick={() => {
                        editor.chain().focus().setColor(c.value).run();
                        setColorOpen(false);
                      }}
                    />
                  ) : (
                    /* 默认色：斜线图标 */
                    <button
                      key="default"
                      type="button"
                      title="默认颜色"
                      className={`rte-color-swatch rte-color-swatch--default${!editor.getAttributes("textStyle").color ? " rte-color-swatch--active" : ""}`}
                      onClick={() => {
                        editor.chain().focus().unsetColor().run();
                        setColorOpen(false);
                      }}
                    >
                      <span className="rte-color-swatch-slash" />
                    </button>
                  ),
                )}
              </div>
            </div>
          )}
        </div>

        <span className="rte-toolbar-divider" />

        {toolbarBtn(
          false,
          () => editor.chain().focus().unsetAllMarks().run(),
          <ClearOutlined />,
          "清除格式",
        )}
      </div>

      {/* 编辑区 */}
      <EditorContent editor={editor} className="rte-content" />
    </div>
  );
}
