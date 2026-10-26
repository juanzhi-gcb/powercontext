---
spec_id: SPEC-ORD-001
title: 订单列表查询
status: active
anchors:
  - demo_project/ordermesh/service.py
  - demo_project/ordermesh/repository.py
keywords:
  - 订单列表
  - list_orders
  - 排序
  - 状态筛选
  - order listing
---

# SPEC-ORD-001 订单列表查询

本规格约束 `OrderService.list_orders` 的稳定行为。任何新筛选条件都不得破坏这里的约定。

## R1 返回范围与排序

`list_orders(customer_id)` 只返回该客户自己的订单，并按 `created_at` 降序排列（最新的订单在前）。
未知客户必须返回空列表，而不是抛出异常。

## R2 状态筛选

`status` 参数可选；传入时只保留 `OrderStatus` 匹配的订单。
`status` 既接受 `OrderStatus` 枚举，也接受其字符串值（如 `"paid"`）。
未知状态必须抛出 `ValueError`，消息包含 `unknown status`。

## R3 金额精度

订单金额 `Order.total` 全程使用 `Decimal`，禁止退化为浮点数比较。

## R4 组合筛选

多个筛选条件同时传入时按逻辑与组合，且结果仍满足 R1 的排序约定。