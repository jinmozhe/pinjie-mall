import type { FreightQuoteInput, ShippingTemplateInput, ShippingTemplateRead } from "@pinjie/api-client";
import { CalculatorOutlined, DeleteOutlined, EditOutlined, PlusOutlined, PoweroffOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Divider, Form, Input, InputNumber, Select, Space, Switch, Tag, message } from "antd";
import { useState } from "react";

import { EditorModal } from "@/components/EditorModal";
import { PageFrame } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { StandardConfirmModal } from "@/components/StandardConfirmModal";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";
import { errorMessage } from "@/lib/api/http";
import { useLockedMutation } from "@/lib/useLockedMutation";
import { provinces } from "./provinces";

function ShippingEditor({ target, close, done }: { target: ShippingTemplateRead | null; close: () => void; done: () => Promise<void> }) {
  const [form] = Form.useForm<ShippingTemplateInput>();
  const [remove, setRemove] = useState<(() => void)>();
  const method = Form.useWatch("pricing_method", form);
  const unit = method === "weight" ? "克" : "件";
  return <EditorModal title={target ? "编辑运费模板" : "新建运费模板"} width={800} onClose={close} onSave={async () => {
    const values = await form.validateFields();
    const input = { ...values, free_shipping_threshold: values.free_shipping_threshold ?? null, excluded_provinces: values.excluded_provinces ?? [] };
    if (target) await commerceApi.updateShipping(target.id, { ...input, revision: target.revision });
    else await commerceApi.createShipping(input);
    message.success("运费模板已保存"); await done(); close();
  }}>
    <Form form={form} layout="vertical" initialValues={target ?? { name: "", pricing_method: "piece", is_active: true, excluded_provinces: [], regions: [{ provinces: [], first_unit: 1, first_price: "0.00", additional_unit: 1, additional_price: "0.00" }] }}>
      <Form.Item name="name" label="模板名称" rules={[{ required: true, whitespace: true, max: 100 }]}><Input maxLength={100} /></Form.Item>
      <Space wrap align="start">
        <Form.Item name="pricing_method" label="计费方式" rules={[{ required: true }]}><Select style={{ width: 160 }} options={[{ value: "piece", label: "按件数" }, { value: "weight", label: "按重量（克）" }]} /></Form.Item>
        <Form.Item name="free_shipping_threshold" label="满额包邮（元，可留空）"><InputNumber<string> stringMode min="0" precision={2} /></Form.Item>
        <Form.Item name="is_active" label="启用" valuePropName="checked"><Switch /></Form.Item>
      </Space>
      <Form.Item name="excluded_provinces" label="不参与满额包邮的省份"><Select mode="multiple" options={provinces} /></Form.Item>
      <Alert type="info" showIcon title="必须保留一条省份为空的默认地区规则；同一省份只能出现一次。" />
      <Form.List name="regions">{(fields, actions) => <>
        {fields.map((field, index) => <div key={field.key}>
          <Divider titlePlacement="start">地区规则 {index + 1}</Divider>
          <Form.Item name={[field.name, "provinces"]} label="省份，留空表示默认地区"><Select mode="multiple" options={provinces} /></Form.Item>
          <Space wrap align="start">
            <Form.Item name={[field.name, "first_unit"]} label={`首${unit}数`} rules={[{ required: true }]}><InputNumber min={1} max={1000000000} precision={0} /></Form.Item>
            <Form.Item name={[field.name, "first_price"]} label="首费（元）" rules={[{ required: true }]}><InputNumber<string> stringMode min="0" precision={2} /></Form.Item>
            <Form.Item name={[field.name, "additional_unit"]} label={`续${unit}数`} rules={[{ required: true }]}><InputNumber min={1} max={1000000000} precision={0} /></Form.Item>
            <Form.Item name={[field.name, "additional_price"]} label="续费（元）" rules={[{ required: true }]}><InputNumber<string> stringMode min="0" precision={2} /></Form.Item>
            <Button danger icon={<DeleteOutlined />} onClick={() => setRemove(() => () => actions.remove(field.name))}>移除规则</Button>
          </Space>
        </div>)}
        <Button icon={<PlusOutlined />} disabled={fields.length >= 100} onClick={() => actions.add({ provinces: [], first_unit: 1, first_price: "0.00", additional_unit: 1, additional_price: "0.00" })}>增加地区规则</Button>
      </>}</Form.List>
    </Form>
    <StandardConfirmModal open={Boolean(remove)} title="移除运费规则" description="移除当前草稿中的这条地区规则，保存模板后生效；取消不会改变草稿。" loading={false} onCancel={() => setRemove(undefined)} onConfirm={async () => { remove?.(); setRemove(undefined); }} />
  </EditorModal>;
}

function QuoteEditor({ target, close }: { target: ShippingTemplateRead; close: () => void }) {
  const [form] = Form.useForm<FreightQuoteInput>();
  const [result, setResult] = useState<string>();
  return <EditorModal title={`运费试算：${target.name}`} onClose={close} onSave={async () => {
    const value = await commerceApi.quote(target.id, await form.validateFields());
    setResult(`运费 ¥${value.freight}${value.free_shipping ? "（包邮）" : ""}`);
  }}>
    <Form form={form} layout="vertical" initialValues={{ pieces: 1, weight_grams: 1000, items_amount: "1.00" }}>
      <Form.Item name="province_code" label="收货省份" rules={[{ required: true }]}><Select options={provinces} /></Form.Item>
      <Form.Item name="pieces" label="件数" rules={[{ required: true }]}><InputNumber min={1} precision={0} /></Form.Item>
      <Form.Item name="weight_grams" label="总重量（克）" rules={[{ required: true }]}><InputNumber min={0} precision={0} /></Form.Item>
      <Form.Item name="items_amount" label="商品金额（元）" rules={[{ required: true }]}><InputNumber<string> stringMode min="0" precision={2} /></Form.Item>
    </Form>
    {result && <Alert type="success" title={result} />}
  </EditorModal>;
}

export function ShippingPage() {
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const allowed = canAccess(admin, "shipping:read");
  const write = canAccess(admin, "shipping:update");
  const [page, setPage] = useState(1);
  const [edit, setEdit] = useState<{ target: ShippingTemplateRead | null }>();
  const [quote, setQuote] = useState<ShippingTemplateRead>();
  const [selected, setSelected] = useState<ShippingTemplateRead[]>([]);
  const query = useQuery({ queryKey: ["commerce-shipping", page], queryFn: () => commerceApi.shipping(page), enabled: allowed });
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["commerce-shipping"] }); };
  const batch = useLockedMutation({ mutationFn: (active: boolean) => commerceApi.shippingStatus({ targets: selected.map(({ id, revision }) => ({ id, revision })), is_active: active }),
    onSuccess: async () => { message.success("模板状态已更新"); setSelected([]); await refresh(); }, onError: (error) => message.error(errorMessage(error)) });
  return <PageFrame title="运费模板" description="按件或按重量计费，配置地区规则并试算运费。">
    {!allowed ? <Alert type="warning" title="无权查看运费模板" /> : <ResourceTable title="运费模板" rows={query.data?.items ?? []} loading={query.isLoading} fetching={query.isFetching} error={query.error} retry={query.refetch}
      page={page} total={query.data?.total} onPage={(next) => { setPage(next); setSelected([]); }}
      selection={write ? { keys: selected.map((row) => row.id), onChange: (_, rows) => setSelected(rows), disabled: batch.isPending } : undefined}
      toolbar={[
        write && <Space key="batch"><Button icon={<PoweroffOutlined />} disabled={!selected.length || batch.isPending} onClick={() => batch.mutate(true)}>批量启用</Button><Button icon={<PoweroffOutlined />} disabled={!selected.length || batch.isPending} onClick={() => batch.mutate(false)}>批量停用</Button></Space>,
        canAccess(admin, "shipping:create") && <Button key="new" type="primary" icon={<PlusOutlined />} onClick={() => setEdit({ target: null })}>新建模板</Button>,
      ]} columns={[
        { title: "名称", dataIndex: "name", ellipsis: true },
        { title: "计费方式", render: (_, row) => row.pricing_method === "piece" ? "按件数" : "按重量（克）" },
        { title: "包邮门槛", render: (_, row) => row.free_shipping_threshold == null ? "未设置" : `¥${row.free_shipping_threshold}` },
        { title: "状态", render: (_, row) => <Tag color={row.is_active ? "success" : "default"}>{row.is_active ? "启用" : "停用"}</Tag> },
        { title: "操作", width: "1%", render: (_, row) => <Space wrap={false}>{write && <Button icon={<EditOutlined />} disabled={batch.isPending} onClick={() => setEdit({ target: row })}>编辑</Button>}<Button icon={<CalculatorOutlined />} onClick={() => setQuote(row)}>试算</Button></Space> },
      ]} />}
    {edit && <ShippingEditor target={edit.target} close={() => setEdit(undefined)} done={refresh} />}
    {quote && <QuoteEditor target={quote} close={() => setQuote(undefined)} />}
  </PageFrame>;
}

export default ShippingPage;
