# T-012: 工作流执行引擎与试运行/监控 API — 实现计划

**日期**: 2026-07-30  
**分支**: `ai/task-b21f88fa-b840-497a-8ddd-4b60937613f8`  
**状态**: plan

---

## 1. 上下文与目标

在现有 Python 脚手架 (`src/sandbox_app/`) 上构建一个工作流执行引擎，支持：

- 异步触发工作流执行并立即返回 `execution_id`
- 按顺序执行 AGENT 节点（使用 stub runner，不依赖真实 LLM）
- 试运行 FULL 模式返回每个节点的执行轨迹与最终输出
- 执行状态查询 API（进度、节点状态）
- 状态快照持久化（崩溃后可恢复进度）
- 可配置的并发上限

---

## 2. 文件变更计划（最小 diff）

### 2.1 新建文件

| # | 文件 | 职责 |
|---|------|------|
| 1 | `src/sandbox_app/models.py` | 数据模型：`WorkflowDef`, `NodeDef`, `Execution`, `NodeExecution`, `ExecutionStatus`, `NodeStatus` |
| 2 | `src/sandbox_app/engine.py` | 核心执行引擎：trigger、sequential executor、stub agent runner、dry-run 逻辑 |
| 3 | `src/sandbox_app/snapshot.py` | 状态快照持久化：save/load 接口，JSON 文件存储 |
| 4 | `src/sandbox_app/config.py` | 执行器配置：`WORKFLOW_CONCURRENCY_LIMIT` 等可配置项 |
| 5 | `tests/test_engine.py` | 引擎测试：顺序成功、节点失败、试运行、状态查询、快照恢复 |
| 6 | `tests/test_snapshot.py` | 快照持久化单元测试 |

### 2.2 修改文件

| # | 文件 | 变更 |
|---|------|------|
| 1 | `src/sandbox_app/__init__.py` | 导出新模块的公共 API |
| 2 | `pyproject.toml` | 无需变更（依赖已满足） |

---

## 3. 架构设计

```
触发 API (trigger) ──► Execution (execution_id, status=pending)
                           │
                           ▼
                     Engine.run_async() ──► 顺序遍历 nodes[]
                           │
                           ▼
                     每个 Node: stub_agent_runner() ──► NodeExecution
                           │                        (status, output, duration)
                           ▼
                     所有节点完成 ──► Execution.status=completed
                           │
                     每步写 Snapshot ──► 崩溃后可从快照恢复
```

### 3.1 核心模型 (`models.py`)

```python
@dataclass
class NodeDef:
    id: str                    # 节点唯一标识
    type: str                  # 固定 "AGENT"
    config: dict               # 节点配置（prompt、inputs 等）

@dataclass
class WorkflowDef:
    id: str
    nodes: list[NodeDef]
    concurrency_limit: int     # 可配置并发上限

class ExecutionStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class NodeStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class NodeExecution:
    node_id: str
    status: NodeStatus
    output: dict | None
    error: str | None
    started_at: str | None
    finished_at: str | None

@dataclass
class Execution:
    id: str
    workflow_id: str
    status: ExecutionStatus
    nodes: list[NodeExecution]
    created_at: str
    updated_at: str
    final_output: dict | None
```

### 3.2 执行引擎 (`engine.py`)

```
Engine
├── trigger(workflow_def) → execution_id          # 异步触发，立即返回
├── run_sync(execution) → Execution                # 同步顺序执行
├── _execute_node(node, mode) → NodeExecution      # 单个节点（stub runner）
├── stub_agent_runner(node_def) → dict             # 模拟 agent 输出
├── dry_run(workflow_def, mode=FULL) → DryRunResult # 试运行
├── get_status(execution_id) → ExecutionStatus     # 状态查询
└── get_progress(execution_id) → Progress          # 进度查询
```

- **顺序执行**: nodes 按定义顺序依次执行，每个节点完成后立即写快照
- **Stub agent runner**: 不调用真实 LLM，基于节点配置返回模拟输出
- **试运行 FULL**: 执行全部节点但标记为 dry_run，返回完整 node_executions 与 final_output
- **快照**: 每个节点执行后调用 `snapshot.save(execution)`

### 3.3 快照持久化 (`snapshot.py`)

```
SnapshotStore
├── save(execution) → None           # 持久化执行状态到 JSON
├── load(execution_id) → Execution   # 从快照恢复
└── _snapshot_path(execution_id) → Path  # 快照文件路径
```

- 存储位置：`<tmpdir>/workflow_snapshots/<execution_id>.json`
- 格式：Execution 的 JSON 序列化

### 3.4 配置 (`config.py`)

```python
WORKFLOW_CONCURRENCY_LIMIT: int = 1       # MVP 顺序执行，默认 1
WORKFLOW_SNAPSHOT_DIR: str | None = None  # 可配置快照目录
```

---

## 4. API 形态

采用纯函数式 API（Python 模块导出），不引入 Web 框架：

```python
from sandbox_app import trigger, get_status, get_progress, dry_run, SnapshotStore

# AC-1: 触发执行
execution_id = trigger(workflow_def)  # → "exec-abc123"

# AC-4: 状态查询
status = get_status(execution_id)     # → ExecutionStatus("running")
progress = get_progress(execution_id) # → Progress(completed=2, total=5, nodes=[...])

# AC-3: 试运行
result = dry_run(workflow_def, mode="FULL")
# → DryRunResult(node_executions=[...], final_output={...})

# AC-5: 快照恢复
store = SnapshotStore()
execution = store.load(execution_id)  # → Execution
```

---

## 5. 测试计划（AC-7：每个 AC 一个测试用例）

| AC | 测试文件 | 测试用例 | 验证点 |
|----|---------|---------|--------|
| AC-1 | `test_engine.py` | `test_trigger_returns_execution_id` | trigger() 返回非空 execution_id，状态为 pending |
| AC-1 | `test_engine.py` | `test_trigger_async_default` | trigger() 立即返回，不阻塞等待执行完成 |
| AC-2 | `test_engine.py` | `test_sequential_node_execution` | 节点按顺序执行，stub runner 被调用，输出正确 |
| AC-2 | `test_engine.py` | `test_node_failure_stops_execution` | 某节点失败后后续节点不执行，状态为 failed |
| AC-3 | `test_engine.py` | `test_dry_run_full_returns_executions` | dry_run(mode=FULL) 返回完整 node_executions 与 final_output |
| AC-4 | `test_engine.py` | `test_get_status_returns_progress` | get_status/get_progress 返回正确的进度与节点状态 |
| AC-5 | `test_snapshot.py` | `test_snapshot_save_and_load` | save 后 load 可恢复完整 Execution 对象 |
| AC-5 | `test_snapshot.py` | `test_snapshot_crash_recovery` | 模拟执行中断，从快照恢复可读取已完成的节点进度 |
| AC-6 | `test_engine.py` | `test_concurrency_limit_configurable` | 修改 config 后并发限制值可读取、可返回 |

---

## 6. 实现顺序

| 步骤 | 做什么 | 产出 |
|------|--------|------|
| 1 | 创建 `models.py` — 所有数据模型 | dataclass + enum |
| 2 | 创建 `config.py` — 配置项 | WORKFLOW_CONCURRENCY_LIMIT |
| 3 | 创建 `snapshot.py` — 快照持久化 | save/load |
| 4 | 创建 `engine.py` — 核心引擎 | trigger, run_sync, stub_runner, dry_run, get_status |
| 5 | 更新 `__init__.py` — 导出公共 API | 对外接口 |
| 6 | 创建 `tests/test_engine.py` — 引擎测试 | AC 1-4, 6-7 |
| 7 | 创建 `tests/test_snapshot.py` — 快照测试 | AC 5 |
| 8 | 运行全量测试 + lint 验证 | `pytest -q && ruff check .` |

---

## 7. 风险与约束

- **无外部依赖**: 不使用 Celery、Redis 等；执行状态存储在内存 dict + JSON 文件快照
- **Stub agent runner**: 不调用真实 LLM API；输出为固定/可配置的模拟数据
- **单线程顺序执行**: MVP 并发上限为 1；`WORKFLOW_CONCURRENCY_LIMIT` 预留了扩展点
- **不引入 Web 框架**: API 全部为 Python 函数导出；未来可包装为 FastAPI/Flask
- **不创建 docs/ stance/ 目录**: 当前仓库无这些目录，按最小 diff 原则不引入
