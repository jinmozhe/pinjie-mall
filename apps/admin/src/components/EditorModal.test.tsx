import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Input } from "antd";
import { describe, expect, it, vi } from "vitest";

import { EditorModal } from "./EditorModal";

describe("商城编辑与审核弹窗", () => {
  it("连续点击只提交一次，提交期间拒绝取消", async () => {
    let finish: (() => void) | undefined;
    const pending = new Promise<void>((resolve) => { finish = resolve; });
    const save = vi.fn(() => pending);
    const close = vi.fn();
    render(<EditorModal title="退款审核" onSave={save} onClose={close}><Input aria-label="审核说明" /></EditorModal>);
    const confirm = screen.getByRole("button", { name: /保\s*存/ });
    act(() => { fireEvent.click(confirm); fireEvent.click(confirm); });
    expect(save).toHaveBeenCalledOnce();
    expect(confirm).toBeDisabled();
    expect(screen.getByRole("button", { name: /取\s*消/ })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape", keyCode: 27 });
    expect(close).not.toHaveBeenCalled();
    await act(async () => { finish?.(); await pending; });
  });

  it("版本冲突保留草稿和弹窗，允许显式重试", async () => {
    const save = vi.fn<() => Promise<void>>().mockRejectedValueOnce(new Error("记录版本已变化")).mockResolvedValueOnce(undefined);
    const close = vi.fn();
    render(<EditorModal title="库存调整" onSave={save} onClose={close}><Input aria-label="调整原因" /></EditorModal>);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "调整原因" }), "盘点修正");
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    expect(await screen.findByText("记录版本已变化")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "调整原因" })).toHaveValue("盘点修正");
    expect(close).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
  });
});
