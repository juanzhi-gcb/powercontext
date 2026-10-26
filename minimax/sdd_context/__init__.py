"""SDD context module:规格驱动开发的任务上下文服务。

The module answers three questions for a development task:

1. Which specification items apply to the task?
2. Which code symbols must be modified?
3. Which tests prove the change works and which ones guard old behaviour?

Engineering material (specs, code, tests) is stored and searched in
seekdb/OceanBase, and task progress is persisted in PowerContext.
"""

__version__ = "1.0.0"
