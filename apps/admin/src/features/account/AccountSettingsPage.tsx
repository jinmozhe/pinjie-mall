import type { AdminProfileUpdateIn } from "@pinjie/api-client";
import { KeyOutlined, SafetyCertificateOutlined, SettingOutlined, UserOutlined } from "@ant-design/icons";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Divider, Form, Input, Space, Tabs, Tag, Typography, App } from "antd";
import { useRef, useState } from "react";

import { PageFrame, formatTime } from "@/components/PageFrame";
import { AvatarUploader } from "@/components/Uploader";
import { useCurrentAdmin } from "@/features/auth";
import { adminApi } from "@/lib/api/admin";
import { errorMessage } from "@/lib/api/http";
import { useLockedMutation } from "@/lib/useLockedMutation";

export function AccountSettingsPage() {
  const { message } = App.useApp();
  const current = useCurrentAdmin();
  const queryClient = useQueryClient();
  const [profileForm] = Form.useForm<AdminProfileUpdateIn>();
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const uploadingAvatarRef = useRef(false);
  const [passwordForm] = Form.useForm<{ current_password: string; new_password: string; confirm_password: string }>();

  const profileMutation = useLockedMutation({
    mutationFn: (values: AdminProfileUpdateIn) => {
      if (uploadingAvatarRef.current) throw new Error("头像正在上传，请完成后再保存");
      return adminApi.updateProfile(values);
    },
    onSuccess: async (updated) => {
      message.success("个人基本信息已更新");
      queryClient.setQueryData(["admin-me"], updated);
      await queryClient.invalidateQueries({ queryKey: ["admin-me"] });
      // 触发页面刷新以同步全局 layout 状态
      window.location.reload();
    },
  });

  const passwordMutation = useMutation({
    mutationFn: (values: { current_password: string; new_password: string }) =>
      adminApi.changePassword(values.current_password, values.new_password),
    onSuccess: () => {
      message.success("密码已成功修改，当前会话已刷新");
      passwordForm.resetFields();
    },
  });

  return (
    <PageFrame title="个人设置" description="管理当前管理员的个人基础资料与账户安全配置。">
      <Card className="workspace-panel">
        <Tabs
          defaultActiveKey="base"
          items={[
            {
              key: "base",
              label: (
                <span>
                  <SettingOutlined /> 基本设置
                </span>
              ),
              children: (
                <div style={{ maxWidth: 640, paddingTop: 12 }}>
                  {profileMutation.isError && (
                    <Alert
                      showIcon
                      type="error"
                      title={errorMessage(profileMutation.error)}
                      style={{ marginBottom: 20 }}
                    />
                  )}
                  <Form
                    form={profileForm}
                    layout="vertical"
                    initialValues={{
                      display_name: current.display_name ?? undefined,
                      avatar: current.avatar ?? undefined,
                    }}
                    onFinish={(values) => profileMutation.mutate(values)}
                    style={{ maxWidth: 480 }}
                  >
                    <Form.Item label="头像" name="avatar">
                      <AvatarUploader disabled={profileMutation.isPending} onUploadingChange={(uploading) => {
                        uploadingAvatarRef.current = uploading;
                        setUploadingAvatar(uploading);
                      }} />
                    </Form.Item>
                    <Form.Item label="登录账号">
                      <Input aria-label="登录账号" value={current.username} disabled prefix={<UserOutlined />} />
                    </Form.Item>
                    <Form.Item
                      label="昵称 / 显示名称"
                      name="display_name"
                      rules={[{ max: 100, message: "显示名称最多 100 个字符" }]}
                    >
                      <Input placeholder="请输入您的显示昵称" maxLength={100} />
                    </Form.Item>
                    <Form.Item style={{ marginTop: 24 }}>
                      <Button type="primary" htmlType="submit" loading={profileMutation.isPending} disabled={uploadingAvatar}>
                        更新基本信息
                      </Button>
                    </Form.Item>
                  </Form>
                </div>
              ),
            },
            {
              key: "security",
              label: (
                <span>
                  <KeyOutlined /> 安全设置
                </span>
              ),
              children: (
                <div style={{ maxWidth: 640, paddingTop: 12 }}>
                  <Typography.Title level={5} style={{ marginBottom: 4 }}>
                    修改账户密码
                  </Typography.Title>
                  <Typography.Paragraph type="secondary" style={{ marginBottom: 20 }}>
                    修改密码后会保留当前登录会话，并自动撤销其他设备上的所有历史会话。
                  </Typography.Paragraph>

                  {passwordMutation.isError && (
                    <Alert
                      showIcon
                      type="error"
                      title={errorMessage(passwordMutation.error)}
                      style={{ marginBottom: 20 }}
                    />
                  )}

                  <Form
                    form={passwordForm}
                    layout="vertical"
                    onFinish={(values) => {
                      passwordMutation.mutate({
                        current_password: values.current_password,
                        new_password: values.new_password,
                      });
                    }}
                  >
                    <Form.Item
                      label="当前密码"
                      name="current_password"
                      rules={[{ required: true, message: "请输入当前正在使用的密码" }, { max: 64 }]}
                    >
                      <Input.Password placeholder="请输入当前密码" autoComplete="current-password" maxLength={64} />
                    </Form.Item>

                    <Form.Item
                      label="新密码"
                      name="new_password"
                      rules={[
                        { required: true, message: "请输入新密码" },
                        { min: 6, max: 64, message: "密码长度必须为 6 至 64 个字符" },
                      ]}
                    >
                      <Input.Password placeholder="请输入 6 至 64 位新密码" autoComplete="new-password" maxLength={64} />
                    </Form.Item>

                    <Form.Item
                      label="确认新密码"
                      name="confirm_password"
                      dependencies={["new_password"]}
                      rules={[
                        { required: true, message: "请再次输入新密码" },
                        ({ getFieldValue }) => ({
                          validator(_, value) {
                            if (!value || getFieldValue("new_password") === value) {
                              return Promise.resolve();
                            }
                            return Promise.reject(new Error("两次输入的新密码不一致"));
                          },
                        }),
                      ]}
                    >
                      <Input.Password placeholder="请再次输入新密码确认" autoComplete="new-password" maxLength={64} />
                    </Form.Item>

                    <Form.Item style={{ marginTop: 24 }}>
                      <Button type="primary" htmlType="submit" loading={passwordMutation.isPending}>
                        修改密码
                      </Button>
                    </Form.Item>
                  </Form>

                  <Divider />

                  <Typography.Title level={5} style={{ marginBottom: 12 }}>
                    账号身份与安全信息
                  </Typography.Title>
                  <Descriptions column={1} size="small" bordered items={[
                    {
                      key: "identity", label: "账号身份",
                      children: current.is_superuser ? (
                        <Tag color="blue" icon={<SafetyCertificateOutlined />}>超级管理员</Tag>
                      ) : <Tag>普通管理员</Tag>,
                    },
                    {
                      key: "roles", label: "所属角色",
                      children: <Space wrap size={[4, 4]}>
                        {current.roles.length > 0 ? (
                          current.roles.map((role) => <Tag key={role.id}>{role.name}</Tag>)
                        ) : (
                          <Typography.Text type="secondary">-</Typography.Text>
                        )}
                      </Space>,
                    },
                    { key: "permissions", label: "拥有权限数", children: <Tag color="cyan">{current.permissions.length} 项有效权限</Tag> },
                    { key: "created_at", label: "注册时间", children: formatTime(current.created_at) },
                  ]} />
                </div>
              ),
            },
          ]}
        />
      </Card>
    </PageFrame>
  );
}

export default AccountSettingsPage;
