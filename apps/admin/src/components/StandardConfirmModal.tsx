import { Alert, Flex, Modal } from "antd";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { errorMessage } from "@/lib/api/http";

type Props = {
  children?: ReactNode;
  description: string;
  loading: boolean;
  open: boolean;
  title: string;
  onCancel: () => void;
  onConfirm: () => Promise<void>;
};

export function StandardConfirmModal({ children, description, loading, open, title, onCancel, onConfirm }: Props) {
  const submittingRef = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();
  const busy = loading || submitting;

  useEffect(() => {
    if (open) setError(undefined);
  }, [open]);

  const confirm = async () => {
    if (!open || loading || submittingRef.current) return;
    // Lock before awaiting validation or the mutation, including clicks in the same render.
    submittingRef.current = true;
    setSubmitting(true);
    setError(undefined);
    try {
      await onConfirm();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <Modal
      cancelButtonProps={{ disabled: busy }}
      cancelText="取消"
      closable={!busy}
      confirmLoading={busy}
      destroyOnHidden
      keyboard={!busy}
      mask={{ closable: !busy }}
      okButtonProps={{ danger: true, disabled: busy }}
      okText="确定"
      open={open}
      title={title}
      onCancel={() => { if (!loading && !submittingRef.current) onCancel(); }}
      onOk={() => void confirm()}
    >
      <Flex vertical gap={12}>
        <Alert showIcon type="warning" title="请确认操作范围" description={description} />
        {error && <Alert showIcon type="error" title={error} />}
        {children}
      </Flex>
    </Modal>
  );
}
