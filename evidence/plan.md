# T-008 实现计划：任务队列、调度策略与生命周期

## 概要

在 `sandbox-app` 工作树中新增三个核心模块（`domain.py`、`queue.py`、`lifecycle.py`）和一个 FastAPI 路由模块（`api.py`），实现任务入队、优先级调度、生命周期状态机及完整测试覆盖。

---

## 目标架构（新增文件）

```
src/sandbox_app/
  __init__.py          ← 不变（保留现有 export）
  core.py              ← 不变
  domain.py            ← 新增：枚举、数据类、错误类型
  queue.py             ← 新增：任务队列引擎（入队/出队/位置查询）
  lifecycle.py         ← 新增：生命周期状态机与历史追踪
  api.py               ← 新增：FastAPI 路由（/queue/*, /tasks/*/timeline）

tests/
  test_core.py         ← 不变
  test_queue.py        ← 新增：AC-1, AC-2, AC-5 覆盖
  test_lifecycle.py    ← 新增：AC-3, AC-4 覆盖
```

**diff 影响面**：仅新增文件 + `pyproject.toml` 增加 `fastapi`、`uvicorn`、`pydantic` 依赖 + `src/sandbox_app/__init__.py` 新增导出（项目无 FastAPI 入口文件，app 实例由 `api.py` 内自创建）。

---

## 步骤 1：领域模型层 `domain.py`

**映射 AC-1, AC-2, AC-3 的数据基础**

| 元素 | 说明 |
|---|---|
| `TaskLifecycleStatus` (StrEnum) | `PENDING / QUEUED / ASSIGNED / RUNNING / SUCCEEDED / FAILED / CANCELLED` |
| `SchedulingPolicy` (StrEnum) | `PRIORITY_FIRST / ROUND_ROBIN / WEIGHTED_RANDOM`(占位) `/ LEAST_LOAD`(占位) |
| `StatusTransition` (Pydantic BaseModel) | `status`, `timestamp`(UTC), `actor`(str), `detail`(str) |
| `QueueEntry` (Pydantic BaseModel) | `queue_entry_id: UUID`, `task_id: UUID`, `priority: int`, `position: int`, `status: TaskLifecycleStatus`, `enqueued_at: datetime`, `status_history: list[StatusTransition]`, `execution_params: dict` |
| `EnqueueResponse` (Pydantic) | `queue_entry_id`, `position`, `estimated_start_time`(可为 None) |
| `TimelineResponse` (Pydantic) | `execution_id`, `status_history`, `current_status`, `total_duration_ms`, `assigned_instance` |
| `QueueFullError` (Exception) | HTTP 映射 429, error_code `QUEUE_FULL` |
| `DuplicateEnqueueError` (Exception) | HTTP 映射 409 |
| `InvalidTransitionError` (Exception) | HTTP 映射 422 |

**关键决策**：
- 使用 Pydantic v2 模型实现序列化/验证，与父项目 FastAPI 生态一致。
- 枚举预留 `WEIGHTED_RANDOM`、`LEAST_LOAD` 为占位值（AC-2 要求"可配置枚举占位"）。

---

## 步骤 2：任务队列引擎 `queue.py`

**映射 AC-1, AC-2, AC-5**

### 2.1 `TaskQueue` 类

```python
class TaskQueue:
    def __init__(self, max_size: int = 10000, policy: SchedulingPolicy = SchedulingPolicy.PRIORITY_FIRST):
        ...
```

| 方法 | 功能 | AC |
|---|---|---|
| `enqueue(task_id, priority=0, params=None) -> EnqueueResponse` | 入队：检查重复 → 插入优先队列 → 返回 queue_entry_id/position | AC-1, AC-5 |
| `dequeue(policy=None) -> QueueEntry` | 出队：按策略取最高优先级(同优先级FIFO)条目，STATUS→ASSIGNED | AC-2 |
| `get_entry(entry_id) -> QueueEntry` | 按 queue_entry_id 查询 | AC-1 |
| `get_position(task_id) -> int \| None` | 查看某 task_id 当前队列位置 | AC-1 |
| `cancel(task_id) -> None` | 从队列移除，状态→CANCELLED | AC-3 |

### 2.2 内部数据结构

- 使用 `heapq` 维护优先级队列。每个元素为 `(-priority, enqueue_order, QueueEntry)` 元组。`-priority` 使最大优先级最先弹出；`enqueue_order` 保证同优先级 FIFO。
- 使用 `dict[UUID, QueueEntry]` 索引 `task_id → entry` 实现 O(1) 重复检测。
- 使用 `dict[UUID, QueueEntry]` 索引 `queue_entry_id → entry` 实现 O(1) 条目查询。

### 2.3 调度策略实现（AC-2 要求"至少实现 PRIORITY_FIRST 与 ROUND_ROBIN 之一"）

- **PRIORITY_FIRST**（默认实现）：高优先级优先；同优先级 FIFO。
- **ROUND_ROBIN**：按优先级分组，每组轮转出队；使用 `itertools.cycle` + 分组队列。
- `dequeue(policy)` 参数覆盖全局默认策略。

### 2.4 QUEUE_FULL 处理（AC-5）

- 构造函数接受 `max_size`（默认 10000，测试时设为 3~5 小值）。
- `enqueue` 入口检查 `len(queue_entries) >= max_size` → 抛出 `QueueFullError`。
- API 层映射为 HTTP 429 + `{"error_code": "QUEUE_FULL"}`。

---

## 步骤 3：生命周期状态机 `lifecycle.py`

**映射 AC-3**

### 3.1 状态转移矩阵

```
PENDING   → QUEUED, CANCELLED
QUEUED    → ASSIGNED, CANCELLED
ASSIGNED  → RUNNING, CANCELLED
RUNNING   → SUCCEEDED, FAILED, CANCELLED
SUCCEEDED → (终态)
FAILED    → (终态)
CANCELLED → (终态)
```

### 3.2 `LifecycleManager` 类

```python
class LifecycleManager:
    def __init__(self, retention_days: int = 90):
        self._histories: dict[UUID, list[StatusTransition]] = {}
        self._valid_transitions: dict[TaskLifecycleStatus, set[TaskLifecycleStatus]] = {...}

    def record_transition(self, execution_id, from_status, to_status, actor, detail) -> StatusTransition
    def get_timeline(self, execution_id) -> list[StatusTransition]
    def get_current_status(self, execution_id) -> TaskLifecycleStatus | None
    def validate_transition(self, from_status, to_status) -> bool
```

### 3.3 关键规则

- 每次状态变更写入带 `timestamp`(UTC)、`actor`、`detail` 的记录。
- 非法转移抛出 `InvalidTransitionError`。
- `get_timeline` 返回完整历史 → 支持 `TimelineResponse` 序列化。
- 每次 `record_transition` 计算 `total_duration_ms`（首条记录到最新记录的时间差）。

---

## 步骤 4：FastAPI 路由 `api.py`

**映射 AC-1, AC-2, AC-3, AC-5**

| 方法 | 路径 | 说明 | AC |
|---|---|---|---|
| `POST` | `/queue/enqueue` | 入队；body: `{task_id, priority?, execution_params?}` → `EnqueueResponse` | AC-1 |
| `POST` | `/queue/dequeue` | 出队；body: `{policy?}` → `QueueEntry` | AC-2 |
| `GET` | `/queue/entry/{entry_id}` | 查询队列条目 | AC-1 |
| `GET` | `/tasks/{task_id}/timeline` | 查询生命周期时间线 → `TimelineResponse` | AC-3 |
| `POST` | `/tasks/{task_id}/transition` | 手动触发状态转移（测试/管理用） | AC-3 |

**错误映射**：
- `QueueFullError` → 429 `{"error_code": "QUEUE_FULL"}`
- `DuplicateEnqueueError` → 409 `{"error_code": "DUPLICATE_TASK"}`
- `InvalidTransitionError` → 422
- 不存在的 entry_id / task_id → 404

**app 实例创建**：在 `api.py` 模块级别创建 `FastAPI` 实例和全局 `TaskQueue`/`LifecycleManager` 单例（后续可替换为 DI）。

---

## 步骤 5：依赖变更 `pyproject.toml`

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.0",
]
```

---

## 步骤 6：测试覆盖

### 6.1 `tests/test_queue.py`（AC-1, AC-2, AC-5）

| 测试 | AC | 说明 |
|---|---|---|
| `test_enqueue_returns_entry_id_and_position` | AC-1 | 入队返回正确的 queue_entry_id 和 position |
| `test_duplicate_enqueue_prevented` | AC-1 | 同一 task_id 重复入队抛 DuplicateEnqueueError |
| `test_enqueue_position_increments` | AC-1 | position 随入队顺序递增 |
| `test_priority_first_ordering` | AC-2 | 高优先级任务先出队 |
| `test_fifo_within_same_priority` | AC-2 | 同优先级按 FIFO 出队 |
| `test_round_robin_policy` | AC-2 | ROUND_ROBIN 策略正确轮转 |
| `test_queue_full_raises_429` | AC-5 | 小上限(max_size=3)下第4个入队抛 QueueFullError |
| `test_queue_full_error_code` | AC-5 | 429 响应体含 error_code QUEUE_FULL |
| `test_dequeue_updates_status` | AC-2 | 出队后条目状态变为 ASSIGNED |

### 6.2 `tests/test_lifecycle.py`（AC-3, AC-4）

| 测试 | AC | 说明 |
|---|---|---|
| `test_full_lifecycle_transitions` | AC-3 | PENDING→QUEUED→ASSIGNED→RUNNING→SUCCEEDED 全链路 |
| `test_status_history_timestamps` | AC-4 | 每次转移写入 timestamp/actor/detail |
| `test_invalid_transition_blocked` | AC-3 | PENDING→RUNNING（跳状态）被拒绝 |
| `test_cancelled_terminal` | AC-3 | CANCELLED 后不可再转移 |
| `test_timeline_queryable` | AC-3 | get_timeline 返回完整历史 |
| `test_timeline_404_for_unknown` | AC-3 | 不存在的 execution_id 返回 404 |

### 6.3 现有测试

保持 `tests/test_core.py` 不变且继续通过。

---

## 执行顺序

| 顺序 | 步骤 | 产出 |
|---|---|---|
| 1 | 创建 `domain.py` | 枚举、模型、错误类 |
| 2 | 创建 `lifecycle.py` | 状态机 + 历史记录 |
| 3 | 创建 `queue.py` | 队列引擎（依赖 domain + lifecycle） |
| 4 | 创建 `api.py` | FastAPI 路由（依赖 queue + lifecycle） |
| 5 | 更新 `pyproject.toml` | 添加 fastapi/uvicorn/pydantic 依赖 |
| 6 | 创建 `tests/test_queue.py` | 队列测试（9 条） |
| 7 | 创建 `tests/test_lifecycle.py` | 生命周期测试（6 条） |
| 8 | 运行全量测试 | 验证 15 条新测 + 2 条旧测全部通过 |

---

## 不变更清单

- `src/sandbox_app/core.py` — 保持 `health()`/`ping()` 不变
- `tests/test_core.py` — 不修改
- `.github/workflows/ci.yml` — 无需变更（`ruff check .` + `pytest -q` 已覆盖）
- 不引入数据库/Redis 依赖（全程内存实现，满足 sandbox 定位）
