import type { BrandInput, BrandRead, BrandUpdate } from "@pinjie/api-client";
import { EditOutlined, PlusOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Input, Switch, Tag, message } from "antd";
import { useState } from "react";

import { EditorModal } from "@/components/EditorModal";
import { PageFrame } from "@/components/PageFrame";
import { ResourceTable } from "@/components/ResourceTable";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { commerceApi } from "@/lib/api/commerce";

function BrandEditor({
  target,
  done,
  close,
}: {
  target: BrandRead | null;
  done: () => Promise<void>;
  close: () => void;
}) {
  const [form] = Form.useForm();
  return (
    <EditorModal
      title={target ? "编辑品牌" : "新建品牌"}
      onClose={close}
      onSave={async () => {
        const values = await form.validateFields();
        if (target) {
          const updatePayload: BrandUpdate = {
            name: values.name.trim(),
            description: values.description?.trim() || "",
            logo_asset_id: values.logo_asset_id?.trim() || null,
            is_active: values.is_active ?? true,
            revision: target.revision,
            sort_order: target.sort_order,
          };
          await commerceApi.updateBrand(target.id, updatePayload);
        } else {
          const createPayload: BrandInput = {
            name: values.name.trim(),
            description: values.description?.trim() || "",
            logo_asset_id: values.logo_asset_id?.trim() || null,
            is_active: values.is_active ?? true,
          };
          await commerceApi.createBrand(createPayload);
        }
        message.success("品牌资料已保存");
        await done();
        close();
      }}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={
          target ?? {
            name: "",
            description: "",
            logo_asset_id: "",
            is_active: true,
          }
        }
      >
        <Form.Item
          name="name"
          label="品牌名称"
          rules={[{ required: true, whitespace: true, max: 100 }]}
        >
          <Input maxLength={100} placeholder="例如：品界甄选" />
        </Form.Item>
        <Form.Item name="description" label="品牌描述">
          <Input.TextArea rows={3} maxLength={500} placeholder="品牌简介（选填）" />
        </Form.Item>
        <Form.Item name="logo_asset_id" label="LOGO 资产标识">
          <Input maxLength={64} placeholder="文件资产 UUID（选填）" />
        </Form.Item>
        <Form.Item name="is_active" label="启用状态" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </EditorModal>
  );
}

export function BrandsPage() {
  const admin = useCurrentAdmin();
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [edit, setEdit] = useState<{ target: BrandRead | null }>();

  const allowed = canAccess(admin, "brands:read");
  const canCreate = canAccess(admin, "brands:create");
  const canUpdate = canAccess(admin, "brands:update");

  const query = useQuery({
    queryKey: ["commerce-brands", page],
    queryFn: () => commerceApi.brands(page),
    enabled: allowed,
  });

  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["commerce-brands"] });
  };

  return (
    <PageFrame title="品牌管理" description="维护商品品牌资料、LOGO 资产引用与启停状态。">
      {!allowed ? (
        <Alert type="warning" title="无权查看品牌列表" />
      ) : (
        <ResourceTable
          title="品牌列表"
          rows={query.data?.items ?? []}
          loading={query.isLoading}
          fetching={query.isFetching}
          error={query.error}
          retry={query.refetch}
          page={page}
          total={query.data?.total}
          onPage={setPage}
          toolbar={[
            canCreate && (
              <Button
                key="new"
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setEdit({ target: null })}
              >
                新建品牌
              </Button>
            ),
          ]}
          columns={[
            { title: "品牌名称", dataIndex: "name", ellipsis: true },
            {
              title: "描述",
              dataIndex: "description",
              ellipsis: true,
              render: (v) => v || "-",
            },
            {
              title: "状态",
              render: (_, row) => (
                <Tag color={row.is_active ? "success" : "default"}>
                  {row.is_active ? "启用" : "停用"}
                </Tag>
              ),
            },
            {
              title: "版本",
              dataIndex: "revision",
              render: (v) => `v${v}`,
            },
            {
              title: "操作",
              width: "1%",
              render: (_, row) =>
                canUpdate ? (
                  <Button
                    icon={<EditOutlined />}
                    onClick={() => setEdit({ target: row })}
                  >
                    编辑
                  </Button>
                ) : null,
            },
          ]}
        />
      )}
      {edit && (
        <BrandEditor
          target={edit.target}
          close={() => setEdit(undefined)}
          done={refresh}
        />
      )}
    </PageFrame>
  );
}

export default BrandsPage;
