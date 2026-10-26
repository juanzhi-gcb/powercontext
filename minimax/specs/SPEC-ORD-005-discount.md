---
spec_id: SPEC-ORD-005
title: 折扣计算
status: active
anchors:
  - demo_project/ordermesh/discount.py
keywords:
  - 折扣
  - discount
  - 四舍五入
  - percent
---

# SPEC-ORD-005 折扣计算

折扣计算与订单查询相互独立，但同属 `ordermesh` 的稳定契约，回归测试必须继续通过。

## R1 分位四舍五入

`apply_percent_discount(total, percent)` 返回折扣后金额，结果保留两位小数，
使用 `ROUND_HALF_UP` 舍入。

## R2 零折扣

`percent` 为 0 时返回与输入相等的金额。

## R3 入参校验

`total` 不是 `Decimal` 时抛出 `TypeError`；`percent` 不在 0 到 100 之间时抛出
`ValueError`，消息包含 `percent`。
