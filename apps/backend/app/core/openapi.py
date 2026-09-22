from typing import Any

OPENAPI_TAGS = [
    {"name": "用户认证", "description": "用户注册、登录、刷新会话和退出登录接口。"},
    {"name": "用户账户", "description": "当前用户资料、密码、登录会话和账户管理接口。"},
    {"name": "管理员认证", "description": "管理员登录、刷新会话、修改密码和敏感操作确认接口。"},
    {"name": "后台管理", "description": "用户、管理员、角色、权限和安全审计管理接口。"},
    {"name": "文件资产", "description": "双域文件上传、管理员资产查询与受控删除接口。"},
    {"name": "系统", "description": "面向应用调用方的公共系统状态接口。"},
    {"name": "系统设置", "description": "受权限保护的站点资料、配置媒体和公开注册设置接口。"},
    {"name": "健康检查", "description": "面向运行平台的存活与就绪探针。"},
]

_RESPONSE_DESCRIPTIONS = {
    "Successful Response": "请求成功",
    "Validation Error": "请求参数校验失败",
}

_FIELD_DESCRIPTIONS = {
    "address_id": "收货地址标识",
    "address_snapshot": "下单时固化的收货地址快照",
    "amount": "业务金额，单位人民币元",
    "auto_confirm_at": "自动确认收货时间",
    "available_amount": "可用余额，单位人民币元",
    "base_amount": "佣金计提基数，单位人民币元",
    "beneficiary_user_id": "佣金受益用户标识",
    "bound_at": "推荐关系首次绑定时间",
    "carrier": "物流承运商",
    "channel": "支付渠道代码",
    "channel_reference": "渠道执行参考号",
    "channel_transaction_id": "渠道交易流水号",
    "confirmed_at": "权威渠道确认时间",
    "content": "评价文本内容",
    "currency": "货币代码",
    "debt_amount": "待追回欠款，单位人民币元",
    "delivered_at": "订单交付完成时间",
    "delivery_reference": "虚拟商品交付凭证",
    "destination_reference": "脱敏收款目标引用",
    "fingerprint": "服务端报价指纹",
    "freight": "本组运费，单位人民币元",
    "freight_amount": "订单运费，单位人民币元",
    "frozen_amount": "冻结余额，单位人民币元",
    "frozen_at": "佣金冻结时间",
    "invitation_code": "会员邀请码",
    "inviter_id": "首次绑定的推荐用户标识",
    "items_amount": "商品合计金额，单位人民币元",
    "level": "推荐佣金层级，最多两级",
    "level_code": "会员等级代码",
    "line_amount": "订单明细金额，单位人民币元",
    "merchant_reference": "商户支付意图参考号",
    "note": "操作说明或核对备注",
    "order_id": "订单标识",
    "order_item_id": "订单明细标识",
    "paid_at": "可信支付确认时间",
    "payment_attempt_id": "支付意图标识",
    "payment_reference": "已确认支付参考号",
    "pieces": "计费件数",
    "product_id": "商品标识",
    "product_name": "商品名称快照",
    "product_revision": "报价时商品版本",
    "product_type": "实物或虚拟商品类型",
    "published_at": "评价发布时间",
    "quantity": "商品数量",
    "quote_fingerprint": "提交时核对的服务端报价指纹",
    "rate": "佣金比例快照",
    "rating": "一至五星评分",
    "reason": "申请原因",
    "recovered_amount": "累计追回佣金，单位人民币元",
    "recovered_at": "最近佣金追回时间",
    "review_note": "审核说明",
    "reviewed_at": "审核时间",
    "reviewed_by_id": "审核管理员标识",
    "revision": "资源并发控制版本",
    "selected": "购物车条目是否选中",
    "settle_after": "允许结算的最早时间",
    "settled_at": "佣金结算时间",
    "shipped_at": "实物发货时间",
    "shipping": "按运费模板分组的报价明细",
    "shipping_template_id": "运费模板标识",
    "sku_code": "商品变体编码快照",
    "sku_id": "商品变体标识",
    "source_hash": "来源账单内容摘要",
    "source_reference": "来源账单参考号",
    "source_user_id": "产生佣金的购买用户标识",
    "specifications": "商品规格名称与取值",
    "template_id": "运费模板标识",
    "total_amount": "订单应付总金额，单位人民币元",
    "tracking_number": "物流运单号",
    "unavailable_reason": "渠道不可用原因",
    "unit_price": "成交单价，单位人民币元",
    "user_id": "用户标识",
    "wallet_type": "佣金或消费钱包类型",
    "weight_grams": "计费重量，单位克",
    "absolute_expires_at": "会话绝对过期时间",
    "access_expires_at": "访问凭据过期时间",
    "action": "操作代码",
    "actor_id": "操作管理员唯一标识",
    "avatar": "管理员头像 URL 或站内资源路径",
    "catalog_version": "权限目录版本",
    "changed_fields": "本次操作涉及的字段摘要",
    "checks": "各项就绪依赖的安全状态摘要",
    "code": "稳定程序代码",
    "completed": "操作是否已经完成",
    "completed_at": "操作完成时间",
    "confirmation_token": "敏感操作短期确认凭据",
    "created_at": "创建时间",
    "ctx": "参数校验错误的补充上下文",
    "data": "响应业务数据",
    "description": "资源说明文本",
    "detail": "请求参数校验错误详情列表",
    "device_name": "登录设备名称",
    "display_name": "展示名称",
    "duration_ms": "请求处理耗时，单位为毫秒",
    "email": "电子邮箱地址",
    "event_type": "安全事件类型代码",
    "file_hash": "文件内容的 SHA-256 哈希值",
    "file_key": "存储驱动中的相对文件键",
    "file_size": "文件大小，单位为字节",
    "expires_at": "凭据过期时间",
    "id": "资源唯一标识",
    "idle_expires_at": "会话空闲过期时间",
    "input": "引发校验错误的输入值，敏感内容可能被省略",
    "ip_address": "请求来源 IP 地址",
    "ip_masked": "脱敏后的请求来源 IP 地址",
    "is_active": "资源当前是否启用",
    "is_current": "是否为当前登录会话",
    "is_superuser": "管理员是否拥有超级管理员身份",
    "items": "当前分页中的资源列表",
    "last_seen_at": "会话最近活动时间",
    "loc": "错误字段在请求中的位置",
    "message": "面向调用方的中文结果消息",
    "method": "HTTP 请求方法",
    "mime_type": "服务端探测得到的真实 MIME 类型",
    "msg": "参数校验错误消息",
    "name": "资源名称",
    "occurred_at": "事件发生时间",
    "original_name": "上传时经过路径剥离的原始文件名",
    "page": "当前页码，从 1 开始",
    "page_size": "每页资源数量",
    "permission_codes": "分配给角色的权限代码列表",
    "permissions": "当前主体拥有的权限代码列表",
    "principal": "当前认证主体信息",
    "principal_id": "认证主体唯一标识",
    "principal_type": "认证主体类型",
    "reason_code": "事件原因代码",
    "release_version": "处理请求的应用发布版本",
    "request_body": "脱敏并截断后的错误 JSON 请求体",
    "request_id": "用于定位本次请求的唯一标识",
    "result": "操作结果代码",
    "revoked_at": "会话撤销时间",
    "role_ids": "分配给管理员的角色唯一标识列表",
    "roles": "管理员当前拥有的角色列表",
    "route_template": "规范化后的 API 路由模板",
    "scene": "受控的文件使用场景",
    "session_id": "登录会话唯一标识",
    "status": "当前状态代码",
    "status_code": "HTTP 响应状态码",
    "storage_driver": "保存文件的存储驱动代码",
    "succeeded": "安全事件是否成功",
    "target_id": "操作目标唯一标识",
    "target_type": "操作目标类型",
    "total": "符合条件的资源总数",
    "total_pages": "符合条件的总页数",
    "trace_id": "用于关联跨组件调用链的唯一标识",
    "type": "参数校验错误类型",
    "updated_at": "最近更新时间",
    "user_agent_summary": "脱敏后的客户端标识摘要",
    "username": "登录用户名",
    "uploader_id": "上传主体唯一标识",
    "uploader_type": "上传主体类型",
    "url": "文件的公开访问 URL 或站内路径",
}


def _localize_schema_fields(schema: dict[str, Any]) -> None:
    components = schema.get("components", {})
    if not isinstance(components, dict):
        return
    schemas = components.get("schemas", {})
    if not isinstance(schemas, dict):
        return
    for component in schemas.values():
        if not isinstance(component, dict):
            continue
        properties = component.get("properties", {})
        if not isinstance(properties, dict):
            continue
        for field_name, field_schema in properties.items():
            if not isinstance(field_schema, dict) or field_schema.get("description"):
                continue
            field_schema["description"] = _FIELD_DESCRIPTIONS.get(
                field_name, "当前业务字段，具体语义由所属请求或响应模型定义"
            )


def localize_openapi_schema(schema: dict[str, Any]) -> dict[str, Any]:
    paths = schema.get("paths", {})
    if isinstance(paths, dict):
        for path_item in paths.values():
            if not isinstance(path_item, dict):
                continue
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.get("responses", {})
                if not isinstance(responses, dict):
                    continue
                for response in responses.values():
                    if not isinstance(response, dict):
                        continue
                    description = response.get("description")
                    if isinstance(description, str):
                        response["description"] = _RESPONSE_DESCRIPTIONS.get(description, description)
    _localize_schema_fields(schema)
    return schema


__all__ = ["OPENAPI_TAGS", "localize_openapi_schema"]
