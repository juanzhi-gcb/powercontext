---
spec_id: SPEC-ORD-003
title: 订单金额下限筛选
status: active
anchors:
  - demo_project/ordermesh/service.py
keywords:
  - min_total
  - 金额下限
  - 筛选条件
  - 边界
  - 阈值
  - 负数
---

# SPEC-ORD-003 订单金额下限筛选

门店页面需要按金额门槛筛订单。`list_orders` 增加可选参数 `min_total`。

## R1 闭区间语义

当 `min_total` 非空时，只返回 `order.total >= min_total` 的订单。
**等于下限的订单必须包含在结果中**，即语义为闭区间。
`min_total` 必须是 `Decimal`、整数或十进制字符串；字符串按十进制解析（例如 `"150.00"`）。
该条件与 `status` 条件同时传入时按逻辑与组合。

## R2 缺省行为

`min_total` 未传或显式传入 `None` 时不得过滤任何订单，其结果必须与旧行为完全一致。

## R3 入参校验

`min_total` 为负数时必须抛出 `ValueError`，消息中包含参数名 `min_total`。
`min_total` 为无法解析为十进制数的字符串（如 `"not-a-number"`）时同样必须抛出
`ValueError`，不得把 `decimal.InvalidOperation` 等底层异常直接暴露给调用方。

## R4 排序保持

加上 `min_total` 之后，结果仍按 `created_at` 降序排列（见 SPEC-ORD-001 R1）。
