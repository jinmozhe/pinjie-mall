import type { ProductRead } from "@pinjie/api-client";

/** 商品首期改版前保留导出，页面路由已明确阻断旧编辑器。 */
export function ProductEditor({
  target,
  close,
  done,
}: {
  target: ProductRead | null;
  close: () => void;
  done: () => Promise<void>;
}) {
  void target;
  void close;
  void done;
  return null;
}
