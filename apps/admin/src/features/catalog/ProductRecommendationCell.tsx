import type { ProductRead, ProductRecommendationUpdate } from "@pinjie/api-client";
import { EditOutlined } from "@ant-design/icons";
import { App, Button, Form, InputNumber, Space, Switch, Tag, Tooltip } from "antd";
import { useEffect, useRef, useState } from "react";

import { commerceApi } from "@/lib/api/commerce";
import { EditorModal } from "@/components/EditorModal";
import { errorMessage } from "@/lib/api/http";
import { useLockedMutation } from "@/lib/useLockedMutation";

type Props = {
  product: ProductRead;
  canUpdate: boolean;
  disabled: boolean;
  lock: (id: string, locked: boolean) => void;
  done: () => Promise<void>;
};

export function ProductRecommendationCell({ product, canUpdate, disabled, lock, done }: Props) {
  const { message } = App.useApp();
  const [editing, setEditing] = useState<ProductRead>();
  const editingRef = useRef<ProductRead | undefined>(undefined);
  useEffect(() => () => { lock(product.id, false); }, [lock, product.id]);
  const [form] = Form.useForm<Pick<ProductRecommendationUpdate, "home_recommend_sort">>();
  const mutation = useLockedMutation({
    mutationFn: (input: ProductRecommendationUpdate) => commerceApi.productRecommendation(product.id, input),
    onMutate: () => { lock(product.id, true); },
    onSuccess: async () => {
      editingRef.current = undefined;
      setEditing(undefined);
      message.success("首页推荐配置已保存");
      await done();
    },
    onError: (error) => { message.error(errorMessage(error)); },
    onSettled: () => { lock(product.id, Boolean(editingRef.current)); },
  });

  const close = () => {
    if (mutation.isPending) return;
    editingRef.current = undefined;
    setEditing(undefined);
    lock(product.id, false);
  };

  return <>
    <Space>
      {canUpdate ? <Switch
        aria-label={`${product.name}首页推荐`}
        checked={product.is_home_recommended}
        checkedChildren="推荐"
        unCheckedChildren="未推荐"
        loading={mutation.isPending}
        disabled={disabled || Boolean(editing) || mutation.isPending}
        onChange={(checked) => mutation.mutate({
          revision: product.revision,
          is_home_recommended: checked,
          home_recommend_sort: product.home_recommend_sort,
        })}
      /> : <Tag>{product.is_home_recommended ? "已推荐" : "未推荐"}</Tag>}
      <Tooltip title="排序值越小越靠前，未设置排最后；相同值按商品创建顺序倒序">
        <span>{product.home_recommend_sort === null ? "未设排序" : `排序 ${product.home_recommend_sort}`}</span>
      </Tooltip>
      {canUpdate && <Button
        size="small"
        icon={<EditOutlined />}
        disabled={disabled || Boolean(editing) || mutation.isPending}
        onClick={() => {
          mutation.reset();
          editingRef.current = product;
          setEditing(product);
          form.setFieldsValue({ home_recommend_sort: product.home_recommend_sort });
          lock(product.id, true);
        }}
      >排序</Button>}
    </Space>
    {editing && <EditorModal
      title={`推荐排序：${editing.name}`}
      onClose={close}
      onSave={async () => {
        const values = await form.validateFields();
        await mutation.mutateAsync({
          revision: editing.revision,
          is_home_recommended: editing.is_home_recommended,
          home_recommend_sort: values.home_recommend_sort ?? null,
        });
      }}
    >
      <Form form={form} component="div" layout="vertical" disabled={mutation.isPending}>
        <Form.Item name="home_recommend_sort" label="推荐排序" extra="非负整数，越小越靠前；清空后排最后。取消推荐会保留排序。"
          rules={[{ type: "integer", min: 0, max: 2147483647, message: "请输入 0 至 2147483647 的整数" }]}
        >
          <InputNumber min={0} max={2147483647} precision={0} placeholder="未设置" style={{ width: "100%" }} />
        </Form.Item>
      </Form>
    </EditorModal>}
  </>;
}
