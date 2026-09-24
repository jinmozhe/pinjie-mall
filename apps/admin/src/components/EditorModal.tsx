import { Alert, Modal } from "antd";
import { useRef, useState, type ReactNode } from "react";

import { errorMessage } from "@/lib/api/http";

// 挂载时固定编辑目标；失败保留表单，用户明确取消或成功后才卸载。
export function EditorModal({ title, children, onSave, onClose, width = 640, blocked = false }: {
  title: string; children: ReactNode; onSave: () => Promise<void>; onClose: () => void; width?: number; blocked?: boolean;
}) {
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const submit = async () => {
    if (lock.current || blocked) return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    try { await onSave(); }
    catch (caught) {
      if (caught && typeof caught === "object" && "errorFields" in caught) setError("请检查表单中标记的字段");
      else setError(errorMessage(caught));
    }
    finally { lock.current = false; setBusy(false); }
  };
  return <Modal open title={title} width={width} okText="保存" cancelText="取消" confirmLoading={busy}
    closable={!busy && !blocked} keyboard={!busy && !blocked} maskClosable={false} okButtonProps={{ disabled: busy || blocked }} cancelButtonProps={{ disabled: busy || blocked }}
    onCancel={() => { if (!lock.current && !blocked) onClose(); }} onOk={() => void submit()}>
    {error && <Alert type="error" showIcon title={error} className="mb-16" />}
    <fieldset disabled={busy} className="editor-fieldset-reset">{children}</fieldset>
  </Modal>;
}
