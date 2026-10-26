---
spec_id: SPEC-ORD-004
title: 查询参数校验约定
status: active
anchors:
  - demo_project/ordermesh/service.py
keywords:
  - 入参校验
  - ValueError
  - 参数名
  - 异常
  - validation
---

# SPEC-ORD-004 查询参数校验约定

本规格统一 `OrderService` 查询接口的错误语义，便于门店页面直接展示错误文案。

## R1 用户输入错误使用 ValueError

调用方传入不可接受的参数值（负数、无法解析的金额、未知枚举值）时，服务层必须抛出
`ValueError`，不得泄漏 `TypeError`、`decimal.InvalidOperation` 等底层实现异常。

## R2 错误消息包含参数名

`ValueError` 的消息必须包含出错的参数名（例如 `min_total`、`status`），
这样上层无需解析异常类型即可定位字段。

## R3 类型错误与取值错误分离

参数类型本身不合法（例如应当传 `Decimal` 却传了 `float`）时可以使用 `TypeError`；
取值不合法时使用 `ValueError`。