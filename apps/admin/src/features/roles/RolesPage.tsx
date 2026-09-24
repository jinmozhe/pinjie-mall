import type { PermissionRead, RoleCreateIn, RoleRead } from "@pinjie/api-client";
import {
  CheckCircleOutlined,
  CheckSquareOutlined,
  ClearOutlined,
  DeleteOutlined,
  EditOutlined,
  MinusSquareOutlined,
  PlusOutlined,
  PlusSquareOutlined,
  SafetyOutlined,
  SearchOutlined,
  StopOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { ProTable } from "@ant-design/pro-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Badge, Button, Checkbox, Empty, Form, Input, Modal, Space, Tag, Tooltip, Tree, Typography, App } from "antd";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { PageFrame, QueryState, formatTime } from "@/components/PageFrame";
import { StandardConfirmModal } from "@/components/StandardConfirmModal";
import { StatusToggleTag } from "@/components/StatusToggleTag";
import { canAccess, useCurrentAdmin } from "@/features/auth";
import { adminApi } from "@/lib/api/admin";
import { errorMessage } from "@/lib/api/http";
import { useLockedMutation } from "@/lib/useLockedMutation";

type RoleForm = RoleCreateIn;
type Confirmation = { description: string; title: string; execute: () => Promise<unknown> };
type PermissionSelectionAction = "all" | "clear" | "invert";
type PermissionTreeNode = {
  children?: PermissionTreeNode[];
  disabled?: boolean;
  key: string;
  label: string;
  searchText: string;
  title: ReactNode;
};

const PERMISSION_GROUPS = [
  { key: "users", label: "用户管理", prefixes: ["users"] },
  { key: "admins", label: "管理员管理", prefixes: ["admins"] },
  { key: "roles", label: "角色与权限", prefixes: ["roles", "permissions"] },
  { key: "security", label: "安全与系统", prefixes: ["security", "system"] },
  { key: "assets", label: "文件资产", prefixes: ["assets"] },
  { key: "settings", label: "系统设置", prefixes: ["settings"] },
] as const;

function permissionTitle(permission: PermissionRead) {
  return (
    <span className="permission-tree-node">
      <span className="permission-tree-name">{permission.name}</span>
      <span className="permission-tree-code">{permission.code}</span>
      {!permission.is_active && <Tag variant="filled">停用</Tag>}
      {!permission.assignable_to_roles && <Tag variant="filled" color="blue">仅超级管理员</Tag>}
    </span>
  );
}

export function buildPermissionTree(permissions: PermissionRead[]): PermissionTreeNode[] {
  const grouped = new Map(PERMISSION_GROUPS.map((group) => [group.key, [] as PermissionRead[]]));
  const unmatched: PermissionRead[] = [];

  for (const permission of permissions) {
    const prefix = permission.code.split(":", 1)[0];
    const group = PERMISSION_GROUPS.find((item) => item.prefixes.some((itemPrefix) => itemPrefix === prefix));
    if (group) grouped.get(group.key)!.push(permission);
    else unmatched.push(permission);
  }

  const groups = [
    ...PERMISSION_GROUPS.map((group) => ({ ...group, permissions: grouped.get(group.key)! })),
    { key: "other", label: "其他权限", prefixes: [], permissions: unmatched },
  ];

  return groups.flatMap((group) => {
    if (group.permissions.length === 0) return [];
    const children = group.permissions.map((permission) => ({
      disabled: !permission.is_active || !permission.assignable_to_roles,
      key: permission.code,
      label: permission.name,
      searchText: `${group.label} ${permission.name} ${permission.code}`.toLocaleLowerCase(),
      title: permissionTitle(permission),
    }));
    return [{
      children,
      key: `__permission_group__:${group.key}`,
      label: group.label,
      searchText: group.label.toLocaleLowerCase(),
      title: <span className="permission-tree-group">{group.label}<span>{children.length}</span></span>,
    }];
  });
}

export function filterPermissionTree(tree: PermissionTreeNode[], query: string): PermissionTreeNode[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return tree;

  return tree.flatMap((group) => {
    if (group.searchText.includes(normalized)) return [group];
    const children = group.children?.filter((permission) => permission.searchText.includes(normalized)) ?? [];
    return children.length > 0 ? [{ ...group, children }] : [];
  });
}

export function filterPermissionCodes(values: string[], permissions: PermissionRead[]): string[] {
  const allowed = new Set(
    permissions.filter((permission) => permission.assignable_to_roles).map((permission) => permission.code),
  );
  return [...new Set(values.filter((value) => allowed.has(value)))];
}

export function updatePermissionSelection(
  action: PermissionSelectionAction,
  selectedCodes: string[],
  permissions: PermissionRead[],
): string[] {
  const selected = new Set(selectedCodes);
  const lockedCodes = permissions
    .filter((permission) => permission.assignable_to_roles && !permission.is_active && selected.has(permission.code))
    .map((permission) => permission.code);
  const activeCodes = permissions
    .filter((permission) => permission.is_active && permission.assignable_to_roles)
    .map((permission) => permission.code);

  if (action === "clear") return lockedCodes;
  if (action === "all") return [...lockedCodes, ...activeCodes];
  return [...lockedCodes, ...activeCodes.filter((code) => !selected.has(code))];
}

export function mergeVisiblePermissionSelection(
  checkedKeys: string[],
  selectedCodes: string[],
  visibleTree: PermissionTreeNode[],
  permissions: PermissionRead[],
): string[] {
  const visibleCodes = new Set(visibleTree.flatMap((group) => group.children?.map((node) => node.key) ?? []));
  const hiddenSelectedCodes = selectedCodes.filter((code) => !visibleCodes.has(code));
  return filterPermissionCodes([...hiddenSelectedCodes, ...checkedKeys], permissions);
}

export function RolesPage() {
  const { message } = App.useApp();
  const current = useCurrentAdmin();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<RoleRead | "new" | null>(null);
  const [permissionTarget, setPermissionTarget] = useState<RoleRead | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [permissionSearch, setPermissionSearch] = useState("");
  const [expandedPermissionKeys, setExpandedPermissionKeys] = useState<string[]>([]);
  const [roleForm] = Form.useForm<RoleForm>();
  const [permissionForm] = Form.useForm<{ permission_codes: string[] }>();
  const selectedPermissionCodes = Form.useWatch("permission_codes", permissionForm) ?? [];
  const roles = useQuery({ queryKey: ["roles", page], queryFn: () => adminApi.roles(page) });
  const canReadPermissions = canAccess(current, "permissions:read");
  const canUpdate = canAccess(current, "roles:update");
  const canDelete = canAccess(current, "roles:delete");
  const canAssignPermissions = canAccess(current, "roles:permissions:assign") && canReadPermissions;
  const permissions = useQuery({ queryKey: ["permissions"], queryFn: adminApi.permissions, enabled: canReadPermissions });
  const permissionTree = useMemo(() => buildPermissionTree(permissions.data ?? []), [permissions.data]);
  const visiblePermissionTree = useMemo(
    () => filterPermissionTree(permissionTree, permissionSearch),
    [permissionSearch, permissionTree],
  );
  const permissionGroupKeys = useMemo(() => permissionTree.map((group) => group.key), [permissionTree]);
  const activePermissionCodes = useMemo(
    () => (permissions.data ?? [])
      .filter((permission) => permission.is_active && permission.assignable_to_roles)
      .map((permission) => permission.code),
    [permissions.data],
  );
  const selectedActiveCount = useMemo(() => {
    const selected = new Set(selectedPermissionCodes);
    return activePermissionCodes.filter((code) => selected.has(code)).length;
  }, [activePermissionCodes, selectedPermissionCodes]);
  const permissionTargetId = permissionTarget?.id;

  useEffect(() => {
    if (permissionTargetId) setExpandedPermissionKeys(permissionGroupKeys);
  }, [permissionGroupKeys, permissionTargetId]);
  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["roles"] }),
      queryClient.invalidateQueries({ queryKey: ["roles-options"] }),
    ]);
  };
  const saveRole = useMutation({
    mutationFn: (values: RoleForm) => editing === "new"
      ? adminApi.createRole(values)
      : adminApi.updateRole(editing!.id, { name: values.name, description: values.description, is_active: values.is_active }),
    onSuccess: async () => { message.success("角色已保存"); setEditing(null); await invalidate(); },
  });
  const batchStatusMutation = useMutation({
    mutationFn: ({ roleIds, isActive }: { roleIds: string[]; isActive: boolean }) =>
      adminApi.setRoleStatusBulk({ role_ids: roleIds, is_active: isActive }),
    onSuccess: async (result, { isActive }) => {
      message.success(`已批量${isActive ? "启用" : "停用"} ${result.completed_count} 个角色`);
      setSelectedRowKeys([]);
      await invalidate();
    },
  });
  const statusMutation = useMutation({
    mutationFn: ({ role, isActive }: { role: RoleRead; isActive: boolean }) =>
      adminApi.updateRole(role.id, { is_active: isActive }),
    onSuccess: async () => {
      message.success("角色状态已更新");
      await invalidate();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const batchDeleteMutation = useMutation({
    mutationFn: (roleIds: string[]) => adminApi.deleteRolesBulk({ role_ids: roleIds }),
    onSuccess: async (result) => {
      message.success(`已批量删除 ${result.completed_count} 个角色`);
      setSelectedRowKeys([]);
      await invalidate();
    },
  });
  const deleteRoleMutation = useMutation({
    mutationFn: (roleId: string) => adminApi.deleteRole(roleId),
    onSuccess: async () => {
      message.success("角色已删除");
      await invalidate();
    },
  });
  const assignPermissionsMutation = useLockedMutation({
    mutationFn: ({ roleId, permissionCodes }: { roleId: string; permissionCodes: string[] }) => {
      if (!permissions.isSuccess) throw new Error("权限目录尚未成功加载，请重试后保存");
      return adminApi.assignPermissions(roleId, filterPermissionCodes(permissionCodes, permissions.data));
    },
    onSuccess: async () => {
      message.success("角色权限已更新，关联管理员会话已撤销");
      setPermissionTarget(null);
      await invalidate();
    },
  });
  const begin = (title: string, description: string, execute: () => Promise<unknown>) =>
    setConfirmation({ title, description, execute });
  const applyPermissionSelection = (action: PermissionSelectionAction) => {
    permissionForm.setFieldValue(
      "permission_codes",
      updatePermissionSelection(action, selectedPermissionCodes, permissions.data ?? []),
    );
  };
  const beginBulkStatusChange = (isActive: boolean) => {
    const roleIds = [...selectedRowKeys];
    void batchStatusMutation
      .mutateAsync({ roleIds, isActive })
      .catch((error: unknown) => message.error(errorMessage(error)));
  };
  const beginBulkDelete = () => {
    const roleIds = [...selectedRowKeys];
    begin(
      `确认批量删除 ${roleIds.length} 个角色`,
      "只有未分配给管理员的角色可以删除。确认后角色及其权限关联将被永久删除。",
      () => batchDeleteMutation.mutateAsync(roleIds),
    );
  };
  const confirmAction = async () => {
    if (!confirmation) return;
    try {
      await confirmation.execute();
      setConfirmation(null);
    } catch (error) {
      message.error(errorMessage(error));
    }
  };

  return (
    <PageFrame title="角色与权限" description="角色可维护，权限目录由源码定义并以只读方式呈现。">
      <QueryState loading={roles.isLoading} error={roles.isError ? errorMessage(roles.error) : undefined} onRetry={() => void roles.refetch()} />
      {roles.data && (
        <ProTable<RoleRead>
          className="responsive-data-table"
          rowKey="id"
          dataSource={roles.data.items}
          search={false}
          options={{
            density: true,
            fullScreen: true,
            reload: () => void roles.refetch(),
            setting: true,
          }}
          cardProps={false}
          headerTitle="角色列表"
          toolBarRender={() => [
            canAccess(current, "roles:create") ? (
              <Button
                key="create"
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => {
                  setEditing("new");
                  roleForm.resetFields();
                  roleForm.setFieldsValue({ is_active: true });
                }}
              >
                新建角色
              </Button>
            ) : null,
          ]}
          rowSelection={
            canUpdate || canDelete
              ? {
                  selectedRowKeys,
                  onChange: (keys) => setSelectedRowKeys(keys.map(String)),
                }
              : false
          }
          tableAlertRender={({ selectedRowKeys: keys }) => <span>已选择 {keys.length} 项</span>}
          tableAlertOptionRender={({ onCleanSelected }) => (
            <Space size={8} wrap={false}>
              {canUpdate && (
                <Button
                  size="small"
                  icon={<CheckCircleOutlined />}
                  disabled={batchStatusMutation.isPending || batchDeleteMutation.isPending}
                  loading={batchStatusMutation.isPending && batchStatusMutation.variables?.isActive}
                  onClick={() => beginBulkStatusChange(true)}
                >
                  批量启用
                </Button>
              )}
              {canUpdate && (
                <Button
                  size="small"
                  danger
                  icon={<StopOutlined />}
                  disabled={batchStatusMutation.isPending || batchDeleteMutation.isPending}
                  loading={batchStatusMutation.isPending && !batchStatusMutation.variables?.isActive}
                  onClick={() => beginBulkStatusChange(false)}
                >
                  批量停用
                </Button>
              )}
              {canDelete && (
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={batchStatusMutation.isPending || batchDeleteMutation.isPending}
                  loading={batchDeleteMutation.isPending}
                  onClick={beginBulkDelete}
                >
                  批量删除
                </Button>
              )}
              <Button type="link" size="small" onClick={onCleanSelected}>
                取消选择
              </Button>
            </Space>
          )}
          scroll={{ x: "max-content" }}
          pagination={{
            current: page,
            pageSize: roles.data.page_size,
            total: roles.data.total,
            showSizeChanger: false,
            onChange: (nextPage) => { setSelectedRowKeys([]); setPage(nextPage); },
          }}
          columns={[
            { title: "角色", dataIndex: "name", render: (_, row) => <div className="table-primary-cell role-primary-cell"><Typography.Text strong>{row.name}</Typography.Text><Badge className="role-code-badge" count={row.code} /></div> },
            { title: "说明", dataIndex: "description", ellipsis: true, responsive: ["lg"], render: (value) => value || "-" },
            { title: "权限数", dataIndex: "permissions", width: 100, render: (_, row) => row.permissions.length },
            { title: "状态", dataIndex: "is_active", width: 90, render: (_, row) => (
              <StatusToggleTag
                active={row.is_active}
                ariaLabel={`${row.is_active ? "停用" : "启用"}角色：${row.code}`}
                interactive={canUpdate}
                loading={statusMutation.isPending && statusMutation.variables?.role.id === row.id}
                readOnlyReason="没有修改角色的权限"
                onToggle={() => statusMutation.mutate({ role: row, isActive: !row.is_active })}
              />
            ) },
            { title: "更新时间", dataIndex: "updated_at", width: 170, responsive: ["xl"], render: (_, row) => formatTime(row.updated_at) },
            {
              title: "操作",
              key: "actions",
              width: "1%",
              onHeaderCell: () => ({ style: { whiteSpace: "nowrap" } }),
              onCell: () => ({ style: { whiteSpace: "nowrap" } }),
              render: (_, row) => (
                <Space className="table-actions" size={[2, 0]} wrap={false}>
                  {canUpdate && <Button type="link" size="small" icon={<EditOutlined />} onClick={() => { setEditing(row); roleForm.setFieldsValue({ code: row.code, name: row.name, description: row.description, is_active: row.is_active }); }}>编辑</Button>}
                  {canAssignPermissions && <Button type="link" size="small" icon={<SafetyOutlined />} onClick={() => { setPermissionSearch(""); setPermissionTarget(row); permissionForm.setFieldsValue({ permission_codes: row.permissions }); }}>权限</Button>}
                  {canDelete && <Button type="link" danger size="small" icon={<DeleteOutlined />} onClick={() => begin("删除未使用角色", "确认后该角色及其权限关联将被永久删除，删除后无法恢复。", () => deleteRoleMutation.mutateAsync(row.id))}>删除</Button>}
                </Space>
              ),
            },
          ]}
        />
      )}

      <Modal open={Boolean(editing)} title={editing === "new" ? "新建角色" : "编辑角色"} okText="保存" confirmLoading={saveRole.isPending} onCancel={() => setEditing(null)} onOk={() => roleForm.submit()}>
        {saveRole.isError && <Alert showIcon type="error" title={errorMessage(saveRole.error)} />}
        <Form<RoleForm> form={roleForm} layout="vertical" onFinish={(values) => saveRole.mutate(values)}>
          <Form.Item label="角色代码" name="code" rules={[{ required: true }, { pattern: /^[a-z][a-z0-9_-]{2,99}$/, message: "使用小写字母、数字、下划线或连字符" }]}><Input disabled={editing !== "new"} /></Form.Item>
          <Form.Item label="名称" name="name" rules={[{ required: true }]}><Input maxLength={100} /></Form.Item>
          <Form.Item label="说明" name="description"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="is_active" valuePropName="checked"><Checkbox>启用角色</Checkbox></Form.Item>
        </Form>
      </Modal>

      <Modal width={820} open={Boolean(permissionTarget)} title={permissionTarget ? `配置 ${permissionTarget.name} 的权限` : "配置权限"} okText="保存" confirmLoading={assignPermissionsMutation.isPending} okButtonProps={{ disabled: !permissions.isSuccess || assignPermissionsMutation.isPending }} cancelButtonProps={{ disabled: assignPermissionsMutation.isPending }} closable={!assignPermissionsMutation.isPending} mask={{ closable: !assignPermissionsMutation.isPending }} keyboard={!assignPermissionsMutation.isPending} onCancel={() => { if (!assignPermissionsMutation.isPending) setPermissionTarget(null); }} onOk={() => permissionForm.submit()}>
        <QueryState loading={permissions.isLoading} error={permissions.isError ? errorMessage(permissions.error) : undefined} empty={permissions.data?.length === 0} onRetry={() => void permissions.refetch()} />
        {assignPermissionsMutation.isError && <Alert showIcon type="error" title={errorMessage(assignPermissionsMutation.error)} />}
        <Form form={permissionForm} layout="vertical" onFinish={({ permission_codes }) => {
          const target = permissionTarget;
          if (!target) return;
          assignPermissionsMutation.mutate({
            roleId: target.id,
            permissionCodes: permission_codes,
          });
        }}>
          <Form.Item name="permission_codes" hidden><Input /></Form.Item>
          <div className="permission-tree-workbench">
            <div className="permission-tree-toolbar">
              <Input
                allowClear
                aria-label="搜索权限"
                disabled={!permissions.isSuccess}
                placeholder="搜索权限名称或代码"
                prefix={<SearchOutlined />}
                value={permissionSearch}
                onChange={(event) => {
                  const value = event.target.value;
                  setPermissionSearch(value);
                  if (value.trim()) setExpandedPermissionKeys(permissionGroupKeys);
                }}
              />
              <div className="permission-tree-tools">
                <Typography.Text className="permission-tree-count" type="secondary">
                  已选 <strong>{selectedActiveCount}</strong> / {activePermissionCodes.length}
                </Typography.Text>
                <Space size={4} wrap>
                  <Button
                    icon={<CheckSquareOutlined />}
                    size="small"
                    disabled={!permissions.isSuccess || selectedActiveCount === activePermissionCodes.length}
                    onClick={() => applyPermissionSelection("all")}
                  >
                    全选
                  </Button>
                  <Button
                    icon={<SwapOutlined />}
                    size="small"
                    disabled={!permissions.isSuccess || activePermissionCodes.length === 0}
                    onClick={() => applyPermissionSelection("invert")}
                  >
                    反选
                  </Button>
                  <Tooltip title="清除全部启用权限，保留已分配的停用权限">
                    <Button
                      icon={<ClearOutlined />}
                      size="small"
                      disabled={!permissions.isSuccess || selectedActiveCount === 0}
                      onClick={() => applyPermissionSelection("clear")}
                    >
                      清空
                    </Button>
                  </Tooltip>
                  <Tooltip title="展开全部">
                    <Button aria-label="展开全部权限分组" icon={<PlusSquareOutlined />} size="small" type="text" onClick={() => setExpandedPermissionKeys(permissionGroupKeys)} />
                  </Tooltip>
                  <Tooltip title="收起全部">
                    <Button aria-label="收起全部权限分组" icon={<MinusSquareOutlined />} size="small" type="text" onClick={() => setExpandedPermissionKeys([])} />
                  </Tooltip>
                </Space>
              </div>
            </div>
            <div className="permission-tree-surface">
              {permissions.isSuccess && visiblePermissionTree.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未找到匹配权限" />
              ) : (
                <Tree
                  blockNode
                  checkable
                  checkedKeys={selectedPermissionCodes}
                  disabled={!permissions.isSuccess}
                  expandedKeys={expandedPermissionKeys}
                  height={420}
                  selectable={false}
                  showLine={{ showLeafIcon: false }}
                  treeData={visiblePermissionTree}
                  onCheck={(keys) => {
                    const checkedKeys = Array.isArray(keys) ? keys : keys.checked;
                    permissionForm.setFieldValue(
                      "permission_codes",
                      mergeVisiblePermissionSelection(
                        checkedKeys.map(String),
                        selectedPermissionCodes,
                        visiblePermissionTree,
                        permissions.data ?? [],
                      ),
                    );
                  }}
                  onExpand={(keys) => setExpandedPermissionKeys(keys.map(String))}
                />
              )}
            </div>
          </div>
        </Form>
      </Modal>

      <StandardConfirmModal
        description={confirmation?.description ?? ""}
        loading={batchDeleteMutation.isPending || deleteRoleMutation.isPending}
        open={Boolean(confirmation)}
        title={confirmation?.title ?? "确认操作"}
        onCancel={() => setConfirmation(null)}
        onConfirm={confirmAction}
      />
    </PageFrame>
  );
}

export default RolesPage;
