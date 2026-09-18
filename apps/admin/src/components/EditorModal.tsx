import { Alert, Modal } from "antd";
import { useRef, useState, type ReactNode } from "react";

import { errorMessage } from "@/lib/api/http";

// 挂载时固定编辑目标；失败保留表单，用户明确取消或成功后才卸载。
export function EditorModal({ title, children, onSave, onClose, width = 640 }: {
  title: string; children: ReactNode; onSave: () => Promise<void>; onClose: () => void; width?: number;
}) {
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const submit = async () => {
    if (lock.current) return;
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
    closable={!busy} keyboard={!busy} maskClosable={false} okButtonProps={{ disabled: busy }} cancelButtonProps={{ disabled: busy }}
    onCancel={() => { if (!lock.current) onClose(); }} onOk={() => void submit()}>
    {error && <Alert type="error" showIcon title={error} style={{ marginBottom: 16 }} />}
    <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>{children}</fieldset>
  </Modal>;
}
