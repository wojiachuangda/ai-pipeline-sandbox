# T-009 实施计划：重试、死信、结果存储与 Trace 关联

## 1. 上下文分析

### 仓库现状
- 最小 Python 3.11+ 项目：`sandbox-app`，仅含 `health()` / `ping()` 两个桩函数
- 测试框架：pytest（`tests/test_core.py`）
- Lint：ruff，CI 通过 GitHub Actions
- 无现有队列、重试、执行或跟踪基础设施

### 任务摘要（来源：goal.md SUB-27～29）
在纯 Python 库层实现重试/死信/执行结果存储/追踪关联四个关注点，无需外部依赖（数据库、消息队列、OpenTelemetry）。所有外部 ID 使用 UUID 桩。

---

## 2. 架构设计

### 2.1 模块划分

```
src/sandbox_app/
├── __init__.py          # 导出新增模块
├── core.py              # 现有健康检查（不变）
├── execution.py         # 执行生命周期数据结构（NEW）
├── retry.py             # 重试 & 死信逻辑（NEW）
└── trace.py             # Trace 生成与输出截断（NEW）

tests/
├── test_core.py         # 现有（不变）
├── test_execution.py    # AC-3 测试（NEW）
├── test_retry.py        # AC-1, AC-2, AC-5 测试（NEW）
└── test_trace.py        # AC-4 测试（NEW）
```

### 2.2 核心类型关系

```
RetryConfig ──→ ExecutionContext ──→ ExecutionResult
                     │                      │
                     ▼                      ▼
              DeadLetterEntry ────→ ExecutionStore
                     │
                     ▼
              DeadLetterQueue
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
       REQUEUE    DISCARD   MANUAL_FIX
```

---

## 3. 逐文件实现计划

### 3.1 `src/sandbox_app/execution.py` — 执行数据模型

| 类型 | 说明 |
|---|---|
| `ExecutionStatus` (enum) | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `DEAD_LETTER` |
| `DeadLetterAction` (enum) | `REQUEUE`, `DISCARD`, `MANUAL_FIX` |
| `ExecutionResult` (dataclass) | `execution_id: str`, `trace_id: str`, `status: ExecutionStatus`, `input_snapshot: dict`, `output: str \| None`, `error: str \| None`, `duration_ms: float \| None`, `logs_url: str \| None`, `created_at: float`, `retry_count: int` |
| `ExecutionStore` (class) | 内存字典存储，支持 `save()`, `get(execution_id)`, `list_by_status()`, 超大输出截断（`max_output_chars` 阈值） |

**输出截断策略**：当 `len(output) > max_output_chars` 时截断并追加 `…[truncated N chars]`。

### 3.2 `src/sandbox_app/retry.py` — 重试与死信

| 类型 | 说明 |
|---|---|
| `RetryConfig` (dataclass) | `max_retries: int = 3`, `base_delay_seconds: float = 1.0`, `backoff_multiplier: float = 2.0`, `max_delay_seconds: float = 60.0` |
| `DeadLetterEntry` (dataclass) | `execution_result: ExecutionResult`, `failure_count: int`, `last_error: str`, `created_at: float` |
| `DeadLetterQueue` (class) | 持有 `list[DeadLetterEntry]`，提供 `push(entry)`, `requeue(execution_id)`, `discard(execution_id)`, `mark_manual_fix(execution_id)`, `list_all()`, `get(execution_id)` |
| `ExecutionContext` (class) | 组合 `RetryConfig` + callback，提供 `execute(fn, *args, **kwargs) -> ExecutionResult`。内部循环：调用 fn → 失败时指数退避重试 → 耗尽后推入 `DeadLetterQueue` |

**重试算法**（指数退避）：
```
delay = min(base_delay * multiplier^(attempt-1), max_delay)
```

### 3.3 `src/sandbox_app/trace.py` — Trace 与日志

| 类型 | 说明 |
|---|---|
| `generate_trace_id()` (function) | 返回 `"trace-" + uuid4().hex[:12]` |
| `generate_execution_id()` (function) | 返回 `"exec-" + uuid4().hex[:12]` |
| `build_logs_url(execution_id)` (function) | 返回本地日志路径桩：`"/logs/{execution_id}.log"` |
| `TraceInfo` (dataclass) | `trace_id: str`, `execution_id: str`, `logs_url: str \| None`, `span_context: dict` |

### 3.4 `src/sandbox_app/__init__.py` — 导出更新

从 `execution`、`retry`、`trace` 三个新模块导出所有公开类型和函数。

---

## 4. 测试计划

### 4.1 `tests/test_retry.py`（覆盖 AC-1, AC-2, AC-5）

| 测试用例 | 覆盖验收标准 |
|---|---|
| `test_retry_succeeds_on_first_attempt` | AC-1：成功路径无重试 |
| `test_retry_succeeds_after_transient_failures` | AC-1：瞬态失败后重试成功 |
| `test_retry_exhausted_with_default_config` | AC-1：默认 max_retries=3 耗尽 |
| `test_retry_config_custom_max_retries_and_backoff` | AC-1：自定义 max_retries/backoff |
| `test_retry_exponential_backoff_timing` | AC-1：验证退避延迟计算 |
| `test_retry_exhausted_enters_dead_letter` | AC-1：耗尽→推入死信 |
| `test_dead_letter_requeue_creates_new_execution` | AC-2：REQUEUE 操作 |
| `test_dead_letter_discard_removes_entry` | AC-2：DISCARD 操作 |
| `test_dead_letter_manual_fix_marks_entry` | AC-2：MANUAL_FIX 操作 |
| `test_retry_exhausted_to_dead_letter_to_requeue` | AC-5：端到端：重试耗尽→死信→REQUEUE→重新执行成功 |

### 4.2 `tests/test_execution.py`（覆盖 AC-3）

| 测试用例 | 覆盖验收标准 |
|---|---|
| `test_execution_result_contains_all_fields` | AC-3：input_snapshot/output/status/duration |
| `test_execution_store_save_and_retrieve` | AC-3：存储与查询 |
| `test_execution_store_list_by_status` | AC-3：按状态过滤 |
| `test_large_output_truncation` | AC-3：超大输出截断 |

### 4.3 `tests/test_trace.py`（覆盖 AC-4）

| 测试用例 | 覆盖验收标准 |
|---|---|
| `test_trace_id_format` | AC-4：trace_id 格式正确 |
| `test_execution_id_format` | AC-4：execution_id 格式正确 |
| `test_execution_result_links_trace_id` | AC-4：execution_id ↔ trace_id 关联 |
| `test_logs_url_in_result` | AC-4：logs_url 存在于结果中 |

---

## 5. 实施步骤（执行顺序）

| 步骤 | 文件 | 操作 | 估计行数 |
|---|---|---|---|
| S1 | `src/sandbox_app/trace.py` | 新建：ID 生成、日志桩 | ~30 行 |
| S2 | `src/sandbox_app/execution.py` | 新建：数据模型、存储 | ~120 行 |
| S3 | `src/sandbox_app/retry.py` | 新建：重试、死信、上下文 | ~140 行 |
| S4 | `src/sandbox_app/__init__.py` | 编辑：添加新模块导出 | ~10 行变更 |
| S5 | `tests/test_trace.py` | 新建：AC-4 测试 | ~40 行 |
| S6 | `tests/test_execution.py` | 新建：AC-3 测试 | ~60 行 |
| S7 | `tests/test_retry.py` | 新建：AC-1,2,5 测试 | ~120 行 |
| S8 | — | 运行 `pytest` + `ruff check .` 验证 | — |

**总估计新增代码**：约 520 行（含测试）

---

## 6. 约束检查

- ✅ **minimal diff**：现有 `core.py`、`test_core.py`、`pyproject.toml` 完全不变；仅新增 3 个模块 + 3 个测试文件 + 编辑 `__init__.py`
- ✅ **零外部依赖**：使用 `dataclasses`, `enum`, `time`, `uuid` — 全部标准库
- ✅ **每 AC 有自动化测试**：见第 4 节
- ✅ **无 secrets**：所有 ID 本地生成，无 API 密钥、无环境变量秘密
- ✅ **纯 Python 3.11+**：使用 `from __future__ import annotations` 与现有代码一致
- ✅ **遵循现有模式**：pytest 测试、ruff lint、CI 即时通过

---

## 7. 验收矩阵

| AC | 描述 | 验证方式 |
|---|---|---|
| AC-1 | max_retries/backoff 可配；耗尽进入死信 | `test_retry.py` 中 retry config + dead letter 测试 |
| AC-2 | 死信 REQUEUE/DISCARD/MANUAL_FIX | `test_retry.py` 中 dead letter 操作测试 |
| AC-3 | 执行结果查询含全字段 + 截断 | `test_execution.py` 全部测试 |
| AC-4 | execution_id ↔ trace_id + logs_url | `test_trace.py` 全部测试 |
| AC-5 | 端到端重试耗尽→死信→REQUEUE | `test_retry_exhausted_to_dead_letter_to_requeue` |
