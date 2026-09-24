import { useState } from "react";
import { Descriptions, Drawer, Space, Tag, Typography, Button } from "antd";
import { EyeOutlined } from "@ant-design/icons";
import type { DurableTaskRead } from "@pinjie/api-client";
import { CommerceList } from "@/components/CommerceList";
import { PageFrame } from "@/components/PageFrame";
import { commerceApi } from "@/lib/api/commerce";

export default function DurableTasksPage() {
  const [selectedTask, setSelectedTask] = useState<DurableTaskRead | null>(null);

  const taskStatusColorMap: Record<string, string> = {
    succeeded: "success",
    attention: "error",
    running: "processing",
  };

  return (
    <PageFrame
      title="异步任务诊断"
      description="只读监控系统持久化异步任务执行状态、重试次数、完成时间及脱敏故障摘要；定位处理卡点与异常。"
    >
      <CommerceList<DurableTaskRead>
        resource="durable-tasks"
        title="异步任务"
        rowKey="id"
        load={commerceApi.durableTasks}
        fields={[
          {
            name: "status",
            label: "任务状态",
            options: [
              { label: "待执行 (pending)", value: "pending" },
              { label: "执行中 (running)", value: "running" },
              { label: "已完成 (succeeded)", value: "succeeded" },
              { label: "需注意 (attention)", value: "attention" },
            ],
          },
          { name: "task_type", label: "任务类型" },
          { name: "business_key", label: "业务键" },
        ]}
        columns={[
          {
            title: "任务类型",
            dataIndex: "task_type",
            render: (type) => (
              <Tag color="geekblue" style={{ fontFamily: "monospace" }}>
                {String(type)}
              </Tag>
            ),
          },
          {
            title: "业务键",
            dataIndex: "business_key",
            ellipsis: true,
            render: (key) => (
              <Typography.Text copyable ellipsis style={{ maxWidth: 220 }}>
                {String(key)}
              </Typography.Text>
            ),
          },
          {
            title: "任务状态",
            dataIndex: "status",
            render: (s) => {
              const map: Record<string, { color: string; label: string }> = {
                pending: { color: "default", label: "待执行" },
                running: { color: "processing", label: "执行中" },
                succeeded: { color: "success", label: "已成功" },
                attention: { color: "error", label: "需注意" },
              };
              const item = map[String(s ?? "")] ?? { color: "default", label: String(s ?? "") };
              return <Tag color={item.color}>{item.label}</Tag>;
            },
          },
          {
            title: "执行/失败/上限",
            render: (_, record) => (
              <Space size="small">
                <span>{record.attempt_count} 次尝试</span>
                <span>/</span>
                <Typography.Text type={record.failure_count > 0 ? "danger" : "secondary"}>
                  {record.failure_count} 失败
                </Typography.Text>
                <span style={{ color: "#999" }}>(上限 {record.max_failures})</span>
              </Space>
            ),
          },
          {
            title: "可用时间",
            dataIndex: "available_at",
            ellipsis: true,
          },
          {
            title: "完成时间",
            dataIndex: "completed_at",
            render: (v) => v || <span style={{ color: "#bfbfbf" }}>未完成</span>,
          },
          {
            title: "最近错误代码",
            dataIndex: "last_error_code",
            ellipsis: true,
            render: (v) => (v ? <Tag color="volcano">{v}</Tag> : "-"),
          },
          {
            title: "错误摘要",
            dataIndex: "last_error_summary",
            ellipsis: true,
            render: (v) =>
              v ? (
                <Typography.Text type="danger" ellipsis style={{ maxWidth: 180 }}>
                  {v}
                </Typography.Text>
              ) : (
                "-"
              ),
          },
          {
            title: "操作",
            key: "action",
            render: (_, record) => (
              <Button
                type="link"
                size="small"
                icon={<EyeOutlined />}
                onClick={() => setSelectedTask(record)}
              >
                诊断详情
              </Button>
            ),
          },
        ]}
      />

      <Drawer
        title="异步任务诊断详情"
        placement="right"
        width={600}
        open={selectedTask !== null}
        onClose={() => setSelectedTask(null)}
      >
        {selectedTask && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="任务标识">
              <Typography.Text copyable>{selectedTask.id}</Typography.Text>
            </Descriptions.Item>
            <Descriptions.Item label="任务类型">
              <Tag color="geekblue">{selectedTask.task_type}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="业务键">
              <Typography.Text copyable>{selectedTask.business_key}</Typography.Text>
            </Descriptions.Item>
            <Descriptions.Item label="执行状态">
              <Tag
                color={taskStatusColorMap[selectedTask.status] ?? "default"}
              >
                {selectedTask.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="状态版本 (revision)">
              {selectedTask.revision}
            </Descriptions.Item>
            <Descriptions.Item label="尝试次数">
              {selectedTask.attempt_count}
            </Descriptions.Item>
            <Descriptions.Item label="失败次数">
              <Typography.Text type={selectedTask.failure_count > 0 ? "danger" : undefined}>
                {selectedTask.failure_count}
              </Typography.Text>
            </Descriptions.Item>
            <Descriptions.Item label="最大重试失败上限">
              {selectedTask.max_failures}
            </Descriptions.Item>
            <Descriptions.Item label="就绪可用时间">
              {selectedTask.available_at}
            </Descriptions.Item>
            <Descriptions.Item label="完成时间">
              {selectedTask.completed_at || "尚未完成"}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {selectedTask.created_at}
            </Descriptions.Item>
            <Descriptions.Item label="最近更新时间">
              {selectedTask.updated_at}
            </Descriptions.Item>
            <Descriptions.Item label="最近错误代码">
              {selectedTask.last_error_code ? (
                <Tag color="volcano">{selectedTask.last_error_code}</Tag>
              ) : (
                "无"
              )}
            </Descriptions.Item>
            <Descriptions.Item label="脱敏错误摘要">
              {selectedTask.last_error_summary ? (
                <Typography.Paragraph type="danger" copyable>
                  {selectedTask.last_error_summary}
                </Typography.Paragraph>
              ) : (
                "无异常记录"
              )}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </PageFrame>
  );
}
