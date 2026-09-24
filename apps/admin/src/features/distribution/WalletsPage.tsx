import { EyeOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Drawer } from "antd";
import { useState } from "react";

import { CommerceList } from "@/components/CommerceList";
import { PageFrame } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { commerceApi } from "@/lib/api/commerce";

function LedgerDrawer({ id, close }: { id: string; close: () => void }) {
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ["wallet-ledgers", id, page], queryFn: () => commerceApi.ledgers(id, page) });
  return <Drawer open title="钱包不可变流水" size={1000} onClose={close}>
    <ResourceTable title="钱包流水" rows={query.data?.items ?? []} loading={query.isLoading} fetching={query.isFetching}
      error={query.error} retry={query.refetch} page={page} total={query.data?.total} onPage={setPage} columns={[
        { title: "流水号", dataIndex: "id", ellipsis: true }, { title: "类型", dataIndex: "entry_type" },
        { title: "可用变化", dataIndex: "amount" }, { title: "冻结变化", dataIndex: "frozen_delta" }, { title: "欠款变化", dataIndex: "debt_delta" },
        { title: "关联类型", dataIndex: "reference_type" }, { title: "关联记录", dataIndex: "reference_id", ellipsis: true }, { title: "入账时间", dataIndex: "created_at" },
      ]} />
  </Drawer>;
}

export default function WalletsPage() {
  const [detail, setDetail] = useState<string>();
  return <PageFrame title="双轨钱包" description="佣金与消费钱包独立记账，不提供人工改余额、互转或伪造打款。">
    <CommerceList resource="wallets" title="钱包" load={commerceApi.wallets} fields={[
      { name: "record_id", label: "钱包号" }, { name: "user_id", label: "会员用户号" },
      { name: "wallet_type", label: "轨道", options: [{ label: "佣金钱包", value: "commission" }, { label: "消费钱包", value: "consumption" }] },
    ]} columns={[
      { title: "钱包号", dataIndex: "id", ellipsis: true }, { title: "会员用户号", dataIndex: "user_id", ellipsis: true },
      { title: "轨道", render: (_, row) => row.wallet_type === "commission" ? "佣金钱包" : "消费钱包" },
      { title: "可用金额", dataIndex: "available_amount" }, { title: "冻结金额", dataIndex: "frozen_amount" }, { title: "欠款", dataIndex: "debt_amount" },
      { title: "更新时间", dataIndex: "updated_at" }, { title: "操作", width: "1%", render: (_, row) => <Button icon={<EyeOutlined />} onClick={() => setDetail(row.id)}>查看流水</Button> },
    ]} />
    {detail && <LedgerDrawer key={detail} id={detail} close={() => setDetail(undefined)} />}
  </PageFrame>;
}
