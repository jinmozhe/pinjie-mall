import type {
  AdoptionRead,
  CandidateRead,
  ProductRead,
  SkuUpdate,
} from "@pinjie/api-client";
import {
  ApartmentOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Checkbox,
  Col,
  Divider,
  Empty,
  Flex,
  Input,
  InputNumber,
  Modal,
  Progress,
  Row,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";

import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";

type VariantDimension = {
  adoption: AdoptionRead;
  allowCustomValue: boolean;
  candidates: CandidateRead[];
};

type BatchSkuDraft = {
  code: string;
  cost_price?: string | null;
  initial_quantity: number;
  is_active: boolean;
  key: string;
  market_price?: string | null;
  price: string;
  selected: boolean;
  selections: Record<string, string>;
  spec_display: string;
  spec_value_ids: string[];
  weight_grams?: number | null;
};

type ComboItem = {
  selections: Record<string, string>;
  specValueIds: string[];
};

// 记录同一客户端会话内上次生成的时间戳前缀，用于秒级防重顺延
let lastGeneratedTimestamp = "";

/**
 * 获取 14 位年月日时分秒时间戳前缀，具备同一客户端会话秒级防重顺延机制
 */
function getUniqueTimestampPrefix(): string {
  const format = (d: Date) => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const hours = String(d.getHours()).padStart(2, "0");
    const minutes = String(d.getMinutes()).padStart(2, "0");
    const seconds = String(d.getSeconds()).padStart(2, "0");
    return `${year}${month}${day}${hours}${minutes}${seconds}`;
  };

  let tsStr = format(new Date());
  if (tsStr <= lastGeneratedTimestamp) {
    const lastYear = Number(lastGeneratedTimestamp.slice(0, 4));
    const lastMonth = Number(lastGeneratedTimestamp.slice(4, 6)) - 1;
    const lastDay = Number(lastGeneratedTimestamp.slice(6, 8));
    const lastHours = Number(lastGeneratedTimestamp.slice(8, 10));
    const lastMinutes = Number(lastGeneratedTimestamp.slice(10, 12));
    const lastSeconds = Number(lastGeneratedTimestamp.slice(12, 14));
    const nextDate = new Date(lastYear, lastMonth, lastDay, lastHours, lastMinutes, lastSeconds + 1);
    tsStr = format(nextDate);
  }
  lastGeneratedTimestamp = tsStr;
  return tsStr;
}

/**
 * 根据时间戳前缀与索引生成 16 位纯数字 SKU 编码（14位时间戳 + 2位序号）
 */
function generateSkuCode(index: number, timestampPrefix?: string): string {
  const prefix = timestampPrefix ?? getUniqueTimestampPrefix();
  const seq = String(index + 1).padStart(2, "0");
  return `${prefix}${seq}`;
}

function safeUUID(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

const noWrapCell = () => ({ style: { whiteSpace: "nowrap" } });

type Props = {
  close: () => void;
  dimensions: VariantDimension[];
  onBusyChange: (busy: boolean) => void;
  onSaved: (product: ProductRead) => Promise<void>;
  open: boolean;
  product: ProductRead;
};

export function BatchDeriveSkuModal({
  close,
  dimensions,
  onBusyChange,
  onSaved,
  open,
  product,
}: Props) {
  const { message } = App.useApp();

  // 每个销售维度当前选中的候选值 ID 列表
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Record<string, string[]>>({});
  // 待派生的草稿 SKU 列表
  const [draftSkus, setDraftSkus] = useState<BatchSkuDraft[]>([]);
  // 提交中状态与进度
  const [submitting, setSubmitting] = useState(false);
  const [progressText, setProgressText] = useState("");
  const [progressPercent, setProgressPercent] = useState(0);

  // 批量填充工具栏输入状态
  const [batchPrice, setBatchPrice] = useState<string | number | null>(null);
  const [batchMarketPrice, setBatchMarketPrice] = useState<string | number | null>(null);
  const [batchCostPrice, setBatchCostPrice] = useState<string | number | null>(null);
  const [batchQuantity, setBatchQuantity] = useState<number | null>(null);

  // 现有未归档的 SKU 组合
  const activeSkus = useMemo(
    () => (product.skus ?? []).filter((sku) => sku.archived_at === null),
    [product.skus],
  );

  // 已有 SKU 的组合特征签名集合（候选值 ID 排序拼接）
  const existingSignatures = useMemo(() => {
    const set = new Set<string>();
    for (const sku of activeSkus) {
      const ids = [...(sku.spec_value_ids ?? [])].sort();
      if (ids.length) {
        set.add(ids.join(","));
      }
    }
    return set;
  }, [activeSkus]);

  // 已有 SKU 编码集合，用于防重
  const existingCodes = useMemo(
    () => new Set(activeSkus.map((sku) => sku.code)),
    [activeSkus],
  );

  // 打开弹窗时初始化：默认勾选所有维度的所有当前有效候选值
  useEffect(() => {
    if (!open) return;
    const initialSelections: Record<string, string[]> = {};
    for (const dimension of dimensions) {
      initialSelections[dimension.adoption.id] = dimension.candidates.map((candidate) => candidate.id);
    }
    setSelectedCandidateIds(initialSelections);
    setSubmitting(false);
    setProgressText("");
    setProgressPercent(0);
    setBatchPrice(null);
    setBatchMarketPrice(null);
    setBatchCostPrice(null);
    setBatchQuantity(null);
  }, [dimensions, open]);

  useEffect(() => {
    onBusyChange(submitting);
    return () => onBusyChange(false);
  }, [onBusyChange, submitting]);

  // 维度选中的候选值对象快速查找表
  const candidatesById = useMemo(() => {
    const map = new Map<string, { display_value: string; id: string; name_snapshot: string }>();
    for (const dimension of dimensions) {
      for (const candidate of dimension.candidates) {
        map.set(candidate.id, {
          id: candidate.id,
          display_value: candidate.display_value,
          name_snapshot: dimension.adoption.name_snapshot,
        });
      }
    }
    return map;
  }, [dimensions]);

  // 当勾选候选值变化时，重新做笛卡尔积计算，并排除已存在的 SKU 组合
  useEffect(() => {
    if (!open) return;

    // 检查是否有任何维度一个候选值都没勾选
    const hasEmptyDimension = dimensions.some(
      (dimension) => !(selectedCandidateIds[dimension.adoption.id]?.length),
    );

    if (hasEmptyDimension || dimensions.length === 0) {
      setDraftSkus([]);
      return;
    }

    // 笛卡尔积计算
    const dimensionList = dimensions.map((d) => ({
      adoptionId: d.adoption.id,
      name: d.adoption.name_snapshot,
      selectedIds: selectedCandidateIds[d.adoption.id] ?? [],
    }));

    const combinations = dimensionList.reduce<ComboItem[]>((currentCombinations, dim) => {
      const next: ComboItem[] = [];
      for (const current of currentCombinations) {
        for (const candidateId of dim.selectedIds) {
          next.push({
            selections: { ...current.selections, [dim.adoptionId]: candidateId },
            specValueIds: [...current.specValueIds, candidateId],
          });
        }
      }
      return next;
    }, [{ selections: {}, specValueIds: [] }]);

    // 过滤掉已有组合
    const batchPrefix = getUniqueTimestampPrefix();
    const existingDraftMap = new Map(draftSkus.map((d) => [d.key, d]));

    const nextDrafts: BatchSkuDraft[] = [];
    let newComboIndex = 0;

    for (const combo of combinations) {
      const signature = [...combo.specValueIds].sort().join(",");
      // 如果已有 SKU 中已经存在该组合，直接跳过
      if (existingSignatures.has(signature)) {
        continue;
      }

      // 如果当前草稿中已有该组合，保留用户之前填写的字段
      const previous = existingDraftMap.get(signature);
      if (previous) {
        nextDrafts.push(previous);
      } else {
        // 构造规格搭配文本
        const specDisplay = dimensions
          .map((dim) => {
            const candId = combo.selections[dim.adoption.id];
            const cand = candId ? candidatesById.get(candId) : undefined;
            return `${dim.adoption.name_snapshot}: ${cand?.display_value ?? candId ?? ""}`;
          })
          .join(" | ");

        nextDrafts.push({
          key: signature,
          selections: combo.selections,
          spec_value_ids: combo.specValueIds,
          spec_display: specDisplay,
          code: generateSkuCode(newComboIndex, batchPrefix),
          price: "0",
          market_price: null,
          cost_price: null,
          weight_grams: null,
          initial_quantity: 0,
          is_active: true,
          selected: true,
        });
        newComboIndex += 1;
      }
    }

    setDraftSkus(nextDrafts);
  }, [selectedCandidateIds, dimensions, existingSignatures, open]);

  // 切换某个维度中候选值的勾选
  const handleToggleCandidate = (adoptionId: string, candidateId: string, checked: boolean) => {
    setSelectedCandidateIds((prev) => {
      const currentList = prev[adoptionId] ?? [];
      const nextList = checked
        ? [...currentList, candidateId]
        : currentList.filter((id) => id !== candidateId);
      return { ...prev, [adoptionId]: nextList };
    });
  };

  // 某个维度全选
  const handleSelectAllDimension = (dimension: VariantDimension) => {
    setSelectedCandidateIds((prev) => ({
      ...prev,
      [dimension.adoption.id]: dimension.candidates.map((c) => c.id),
    }));
  };

  // 某个维度清空勾选
  const handleUnselectAllDimension = (dimension: VariantDimension) => {
    setSelectedCandidateIds((prev) => ({
      ...prev,
      [dimension.adoption.id]: [],
    }));
  };

  // 批量应用工具栏数值
  const handleBatchApply = () => {
    const hasPrice = batchPrice !== null && batchPrice !== undefined && batchPrice !== "";
    const hasMarketPrice = batchMarketPrice !== null && batchMarketPrice !== undefined && batchMarketPrice !== "";
    const hasCostPrice = batchCostPrice !== null && batchCostPrice !== undefined && batchCostPrice !== "";
    const hasQuantity = batchQuantity !== null && batchQuantity !== undefined;

    if (!hasPrice && !hasMarketPrice && !hasCostPrice && !hasQuantity) {
      message.warning("请至少输入一项要批量填充的数据（售价、划线价、成本价或初始库存）");
      return;
    }

    if (!draftSkus.length) {
      message.info("暂无可操作的待派生 SKU 组合");
      return;
    }

    setDraftSkus((prev) => prev.map((sku) => {
      // 仅对本次勾选的行（或全部行）应用
      if (!sku.selected) return sku;
      const next = { ...sku };
      if (hasPrice) next.price = String(batchPrice);
      if (hasMarketPrice) next.market_price = String(batchMarketPrice);
      if (hasCostPrice) next.cost_price = String(batchCostPrice);
      if (hasQuantity) next.initial_quantity = Number(batchQuantity);
      return next;
    }));

    const appliedFields: string[] = [];
    if (hasPrice) appliedFields.push("售价");
    if (hasMarketPrice) appliedFields.push("划线价");
    if (hasCostPrice) appliedFields.push("成本价");
    if (hasQuantity) appliedFields.push("初始库存");
    message.success(`已成功批量应用至勾选的 SKU 组合【${appliedFields.join("、")}】`);
  };

  // 重新生成全部待派生编码
  const handleRegenerateCodes = () => {
    if (!draftSkus.length) {
      message.info("暂无可操作的待派生 SKU 组合");
      return;
    }
    const batchPrefix = getUniqueTimestampPrefix();
    setDraftSkus((prev) => prev.map((sku, index) => ({
      ...sku,
      code: generateSkuCode(index, batchPrefix),
    })));
    message.success(`已重新为全部 ${draftSkus.length} 个待派生 SKU 组合生成 16 位唯一编码`);
  };

  // 更新某行数据
  const updateDraftRow = (key: string, patch: Partial<BatchSkuDraft>) => {
    setDraftSkus((prev) => prev.map((sku) => (sku.key === key ? { ...sku, ...patch } : sku)));
  };

  // 移除某行
  const removeDraftRow = (key: string) => {
    setDraftSkus((prev) => prev.filter((sku) => sku.key !== key));
  };

  // 全选/取消全选待派生草稿行
  const selectedDraftCount = draftSkus.filter((sku) => sku.selected).length;
  const isAllDraftSelected = draftSkus.length > 0 && selectedDraftCount === draftSkus.length;

  const handleToggleSelectAllDrafts = (checked: boolean) => {
    setDraftSkus((prev) => prev.map((sku) => ({ ...sku, selected: checked })));
  };

  // 提交并批量创建 SKU
  const handleSubmit = async () => {
    const selectedRows = draftSkus.filter((sku) => sku.selected);
    if (!selectedRows.length) {
      message.warning("请至少勾选一个要派生并创建的 SKU 组合");
      return;
    }

    if (activeSkus.length + selectedRows.length > 100) {
      message.error(`商品 SKU 总数最多 100 个。当前已有 ${activeSkus.length} 个，本次勾选 ${selectedRows.length} 个，已超出上限。`);
      return;
    }

    // 校验编码与价格
    const codeSet = new Set<string>();
    for (const [index, row] of selectedRows.entries()) {
      const code = row.code.trim();
      if (!code) {
        message.error(`第 ${index + 1} 个待派生 SKU 缺少编码`);
        return;
      }
      if (!/^[A-Za-z0-9_-]+$/.test(code)) {
        message.error(`第 ${index + 1} 个待派生 SKU 编码【${code}】格式不合法，只能包含字母、数字、下划线和连字符`);
        return;
      }
      if (codeSet.has(code)) {
        message.error(`待派生列表中存在重复的 SKU 编码：${code}`);
        return;
      }
      if (existingCodes.has(code)) {
        message.error(`SKU 编码【${code}】与商品已有 SKU 重复，请重新生成或修改`);
        return;
      }
      codeSet.add(code);

      const priceNum = Number(row.price);
      if (isNaN(priceNum) || priceNum < 0) {
        message.error(`第 ${index + 1} 个待派生 SKU【${code}】售价必须为大于等于 0 的有效数字`);
        return;
      }
    }

    setSubmitting(true);
    let currentProduct = product;
    let successCount = 0;

    try {
      for (const [idx, row] of selectedRows.entries()) {
        const currentStep = idx + 1;
        const total = selectedRows.length;
        setProgressText(`正在保存第 ${currentStep} / ${total} 个 SKU：${row.code}...`);
        setProgressPercent(Math.floor(((idx) / total) * 100));

        // 1. 调用 writeSku 创建单个 SKU，严格携带最新的 currentProduct.revision
        const skuInput: SkuUpdate = {
          code: row.code.trim(),
          price: String(row.price),
          cost_price: row.cost_price ? String(row.cost_price) : null,
          market_price: row.market_price ? String(row.market_price) : null,
          weight_grams: row.weight_grams ?? null,
          is_active: row.is_active,
          spec_value_ids: row.spec_value_ids,
          revision: currentProduct.revision,
        };

        currentProduct = await commerceApi.writeSku(product.id, skuInput);

        // 2. 如果填写了初始库存且大于 0，调用库存调整接口初始化流水
        if (row.initial_quantity && row.initial_quantity > 0) {
          const createdSku = currentProduct.skus.find((s) => s.code === row.code.trim());
          if (createdSku) {
            setProgressText(`正在初始化第 ${currentStep} / ${total} 个 SKU 库存流水...`);
            const inv = await commerceApi.inventory(createdSku.id);
            await commerceApi.adjustInventory(createdSku.id, {
              request_id: safeUUID(),
              revision: inv.revision,
              quantity_delta: row.initial_quantity,
              reason: "批量派生初始可售库存",
            });
          }
        }

        successCount += 1;
      }

      setProgressPercent(100);
      setProgressText(`成功创建全部 ${successCount} 个 SKU！`);
      await onSaved(currentProduct);
      message.success(`已成功批量派生并创建 ${successCount} 个 SKU 组合！`);
      close();
    } catch (error) {
      if (successCount > 0) {
        // 部分保存成功时，同步更新最新商品状态
        await onSaved(currentProduct);
        message.warning(`已保存前 ${successCount} 个 SKU，后续处理中断：${errorMessage(error)}`);
      } else {
        message.error(`批量派生失败：${errorMessage(error)}`);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ColumnsType<BatchSkuDraft> = [
    {
      title: (
        <Checkbox
          checked={isAllDraftSelected}
          indeterminate={selectedDraftCount > 0 && selectedDraftCount < draftSkus.length}
          onChange={(e) => handleToggleSelectAllDrafts(e.target.checked)}
        />
      ),
      dataIndex: "selected",
      key: "selected",
      width: 50,
      align: "center",
      onHeaderCell: noWrapCell,
      onCell: noWrapCell,
      render: (checked: boolean, row) => (
        <Checkbox
          checked={checked}
          disabled={submitting}
          onChange={(e) => updateDraftRow(row.key, { selected: e.target.checked })}
        />
      ),
    },
    {
      title: "规格搭配",
      dataIndex: "spec_display",
      key: "spec_display",
      width: 220,
      onHeaderCell: noWrapCell,
      onCell: noWrapCell,
      render: (text: string) => (
        <Tooltip title={text}>
          <Tag
            color="blue"
            style={{
              maxWidth: 200,
              textOverflow: "ellipsis",
              overflow: "hidden",
              whiteSpace: "nowrap",
            }}
          >
            {text}
          </Tag>
        </Tooltip>
      ),
    },
    {
      title: "SKU 编码",
      dataIndex: "code",
      key: "code",
      width: 180,
      onHeaderCell: noWrapCell,
      onCell: noWrapCell,
      render: (code: string, row) => (
        <Input
          size="small"
          maxLength={100}
          value={code}
          disabled={submitting}
          onChange={(e) => updateDraftRow(row.key, { code: e.target.value })}
          placeholder="16位唯一条码"
        />
      ),
    },
    {
      title: "售价 (元)",
      dataIndex: "price",
      key: "price",
      width: 120,
      onHeaderCell: noWrapCell,
      onCell: noWrapCell,
      render: (price: string, row) => (
        <InputNumber
          size="small"
          min="0"
          precision={2}
          stringMode
          prefix="¥"
          value={price}
          disabled={submitting}
          onChange={(val) => updateDraftRow(row.key, { price: val ? String(val) : "0" })}
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "划线价 (元)",
      dataIndex: "market_price",
      key: "market_price",
      width: 120,
      onHeaderCell: noWrapCell,
      onCell: noWrapCell,
      render: (val: string | null, row) => (
        <InputNumber
          size="small"
          min="0"
          precision={2}
          stringMode
          prefix="¥"
          value={val ?? undefined}
          disabled={submitting}
          onChange={(newVal) => updateDraftRow(row.key, { market_price: newVal ? String(newVal) : null })}
          placeholder="选填"
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "成本价 (元)",
      dataIndex: "cost_price",
      key: "cost_price",
      width: 120,
      onHeaderCell: noWrapCell,
      onCell: noWrapCell,
      render: (val: string | null, row) => (
        <InputNumber
          size="small"
          min="0"
          precision={2}
          stringMode
          prefix="¥"
          value={val ?? undefined}
          disabled={submitting}
          onChange={(newVal) => updateDraftRow(row.key, { cost_price: newVal ? String(newVal) : null })}
          placeholder="选填"
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "初始库存 (件)",
      dataIndex: "initial_quantity",
      key: "initial_quantity",
      width: 110,
      onHeaderCell: noWrapCell,
      onCell: noWrapCell,
      render: (qty: number, row) => (
        <InputNumber
          size="small"
          min={0}
          max={1000000000}
          precision={0}
          value={qty}
          disabled={submitting}
          onChange={(val) => updateDraftRow(row.key, { initial_quantity: Number(val ?? 0) })}
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "启用销售",
      dataIndex: "is_active",
      key: "is_active",
      width: 90,
      align: "center",
      onHeaderCell: noWrapCell,
      onCell: noWrapCell,
      render: (active: boolean, row) => (
        <Switch
          size="small"
          checked={active}
          disabled={submitting}
          onChange={(checked) => updateDraftRow(row.key, { is_active: checked })}
        />
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 60,
      align: "center",
      onHeaderCell: noWrapCell,
      onCell: noWrapCell,
      render: (_, row) => (
        <Button
          type="text"
          danger
          size="small"
          icon={<DeleteOutlined />}
          disabled={submitting}
          title="移除此待派生组合"
          onClick={() => removeDraftRow(row.key)}
        />
      ),
    },
  ];

  return (
    <Modal
      open={open}
      title={
        <Space>
          <ApartmentOutlined />
          <span>批量派生 SKU：{product.name}</span>
        </Space>
      }
      width={1100}
      closable={!submitting}
      keyboard={!submitting}
      mask={{ closable: !submitting }}
      onCancel={() => { if (!submitting) close(); }}
      footer={[
        <Button key="cancel" disabled={submitting} onClick={close}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={submitting}
          disabled={!draftSkus.length || selectedDraftCount === 0}
          onClick={() => void handleSubmit()}
        >
          {submitting ? "正在批量创建..." : `确认派生并创建（${selectedDraftCount} 个 SKU）`}
        </Button>,
      ]}
    >
      <Alert
        showIcon
        type="info"
        title="勾选本次需要组合的规格候选值，系统将自动进行笛卡尔积计算，并自动跳过已存在的 SKU 组合。"
        description="支持统一预设单价、划线价、成本价及初始库存，也可在下方列表中针对特定规格微调。"
        style={{ marginBottom: 16 }}
      />

      {/* 销售规格候选值勾选区 */}
      <div style={{ marginBottom: 16, backgroundColor: "#fafafa", padding: "12px 16px", borderRadius: 6, border: "1px solid #f0f0f0" }}>
        <Typography.Text strong style={{ fontSize: 14, display: "block", marginBottom: 8 }}>
          参与本次派生的销售规格候选值：
        </Typography.Text>
        <Flex vertical gap={12}>
          {dimensions.map((dimension) => {
            const selectedIds = selectedCandidateIds[dimension.adoption.id] ?? [];
            const isAllSelected = selectedIds.length === dimension.candidates.length && dimension.candidates.length > 0;
            return (
              <Row key={dimension.adoption.id} gutter={[12, 0]} align="middle">
                <Col flex="0 0 160px">
                  <Space size={6}>
                    <Typography.Text style={{ fontWeight: 500 }}>{dimension.adoption.name_snapshot}</Typography.Text>
                    <Tag color="blue" style={{ marginInlineEnd: 0 }}>
                      {selectedIds.length}/{dimension.candidates.length}
                    </Tag>
                  </Space>
                </Col>
                <Col flex="auto">
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "6px 14px" }}>
                    {dimension.candidates.length > 1 && (
                      <Button
                        type="link"
                        size="small"
                        disabled={submitting}
                        style={{ padding: 0, height: "auto", fontSize: 13 }}
                        onClick={() => (isAllSelected ? handleUnselectAllDimension(dimension) : handleSelectAllDimension(dimension))}
                      >
                        {isAllSelected ? "取消全选" : "全选"}
                      </Button>
                    )}
                    {dimension.candidates.map((candidate) => {
                      const isChecked = selectedIds.includes(candidate.id);
                      return (
                        <Checkbox
                          key={candidate.id}
                          checked={isChecked}
                          disabled={submitting}
                          onChange={(e) => handleToggleCandidate(dimension.adoption.id, candidate.id, e.target.checked)}
                        >
                          {candidate.display_value}
                        </Checkbox>
                      );
                    })}
                  </div>
                </Col>
              </Row>
            );
          })}
        </Flex>
      </div>

      {/* 批量填充工具栏 */}
      <div
        style={{
          backgroundColor: "#f7f8fa",
          border: "1px solid #ebeef5",
          borderRadius: 6,
          padding: "10px 14px",
          marginBottom: 16,
        }}
      >
        <Row gutter={[12, 8]} align="middle">
          <Col flex="0 0 auto">
            <span style={{ fontWeight: 500, color: "#262626", fontSize: 13 }}>
              批量填充默认值：
            </span>
          </Col>
          <Col flex="0 0 auto">
            <InputNumber
              style={{ width: 130 }}
              placeholder="售价 (元)"
              prefix="¥"
              min={0}
              precision={2}
              stringMode
              disabled={submitting}
              value={batchPrice ?? undefined}
              onChange={(val) => setBatchPrice(val ?? null)}
            />
          </Col>
          <Col flex="0 0 auto">
            <InputNumber
              style={{ width: 130 }}
              placeholder="划线价 (元)"
              prefix="¥"
              min={0}
              precision={2}
              stringMode
              disabled={submitting}
              value={batchMarketPrice ?? undefined}
              onChange={(val) => setBatchMarketPrice(val ?? null)}
            />
          </Col>
          <Col flex="0 0 auto">
            <InputNumber
              style={{ width: 130 }}
              placeholder="成本价 (元)"
              prefix="¥"
              min={0}
              precision={2}
              stringMode
              disabled={submitting}
              value={batchCostPrice ?? undefined}
              onChange={(val) => setBatchCostPrice(val ?? null)}
            />
          </Col>
          <Col flex="0 0 auto">
            <InputNumber
              style={{ width: 130 }}
              placeholder="初始库存 (件)"
              min={0}
              max={1000000000}
              precision={0}
              disabled={submitting}
              value={batchQuantity ?? undefined}
              onChange={(val) => setBatchQuantity(val ?? null)}
            />
          </Col>
          <Col flex="auto">
            <Space size={8}>
              <Button type="primary" disabled={submitting} onClick={handleBatchApply}>
                应用到勾选行
              </Button>
              <Button
                disabled={submitting}
                onClick={() => {
                  setBatchPrice(null);
                  setBatchMarketPrice(null);
                  setBatchCostPrice(null);
                  setBatchQuantity(null);
                }}
              >
                清空输入
              </Button>
              <Button
                icon={<ReloadOutlined />}
                disabled={submitting || !draftSkus.length}
                onClick={handleRegenerateCodes}
              >
                重新生成编码
              </Button>
            </Space>
          </Col>
        </Row>
      </div>

      {submitting && (
        <div style={{ marginBottom: 16 }}>
          <Progress percent={progressPercent} status="active" />
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            {progressText}
          </Typography.Text>
        </div>
      )}

      {/* 待派生 SKU 列表 */}
      <Divider orientation="horizontal" titlePlacement="start" plain style={{ margin: "12px 0" }}>
        <span>待派生新 SKU 列表（共 {draftSkus.length} 个新组合，已勾选 {selectedDraftCount} 个）</span>
      </Divider>

      {draftSkus.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="所选规格维度的搭配已全部存在对应 SKU，或未选择候选值"
        />
      ) : (
        <Table<BatchSkuDraft>
          rowKey="key"
          size="small"
          pagination={false}
          scroll={{ x: "max-content", y: 360 }}
          dataSource={draftSkus}
          columns={columns}
        />
      )}
    </Modal>
  );
}
