# T-007 任务定义、触发器、优先级与依赖 — 实现计划

## 1. 现状

| 项目 | 技术栈 |
|------|--------|
| 语言 | Python 3.11+ |
| 构建 | setuptools (`pyproject.toml`) |
| 测试 | pytest >= 8.0，`tests/` 目录 |
| Lint | ruff（行宽 100） |
| CI | GitHub Actions (`ci.yml`)，包含 lint + test |
| 业务代码 | `src/sandbox_app/` 包（目前只有 `core.py`：`health()`/`ping()`） |
| 数据库 | 无。根据 constraints（minimal diff, no secrets），使用内存字典存储，不引入外部持久化。 |

任务 T-007 对应的目标子任务（goal.md SUB-20~23）在仓库中不存在存根文件——本计划完全基于 AC 驱动。

---

## 2. 模块拆分（minimal diff）

### 2.1 `src/sandbox_app/task.py` — 任务领域模型（NEW）

纯数据类（dataclass），无外部依赖。

```
字段：
  task_id: str
  name: str
  type: "SYNC" | "ASYNC" | "SCHEDULED"
  agent_id: str
  input_schema: dict | None
  status: "INITIALIZED" | "PENDING" | "RUNNING" | "COMPLETED" | "FAILED"
  priority: int  (1–10, 默认 5)
  trigger: Trigger | None
  dependencies: DependencyGraph
  created_at: float
  updated_at: float
```

### 2.2 `src/sandbox_app/trigger.py` — 触发器（NEW）

```
Trigger 联合类型（Union[discriminated]）：
  CronTrigger: expression (str, 经校验)
  EventTrigger: event_type (str)

校验：
  - CRON_PATTERN = r'^(\*|[0-5]?\d) (\*|1?\d|2[0-3]) (\*|[1-2]?\d|3[01]) (\*|1[0-2]?|[1-9]) (\*|[0-6])$'
  - 非法的 Cron 表达式 → raise ValueError（包装为 INVALID_CRON 错误码在 API 层）
  - 5 字段：分 时 日 月 星期（标准 cron 5位）
```

### 2.3 `src/sandbox_app/priority.py` — 优先级（可合并到 task.py）

优先级纯粹是 1–10 int 校验，不拆为独立文件。

### 2.4 `src/sandbox_app/dependency.py` — 任务依赖（NEW）

```
DependencyGraph:
  - type: "NONE" | "SEQUENTIAL" | "AND_PARALLEL" | "OR_PARALLEL"
  - depends_on: list[str]  （task_id 列表）

循环检测：
  - 插入依赖时对全图做 DFS 环路检测
  - 发现循环 → raise CircularDependencyError(task_id_chain)
  - 错误码映射 → CIRCULAR_TASK_DEPENDENCY
```

### 2.5 `src/sandbox_app/api.py` — 对外 API（NEW）

薄封装层，收敛所有业务操作：

```python
def create_task(...) -> dict:          # 返回 task_id, status=INITIALIZED
def update_priority(task_id, pri) -> dict:
def set_dependency(task_id, dep_type, depends_on) -> dict:
def get_task(task_id) -> dict | None:
def list_tasks() -> list[dict]:
```

所有错误通过自定义异常抛出，API 层统一捕获并返回错误码字符串。

---

## 3. 错误码设计

| 错误 | 含义 |
|------|------|
| `INVALID_CRON` | Cron 表达式校验失败 |
| `CIRCULAR_TASK_DEPENDENCY` | 添加依赖会导致循环 |
| `INVALID_PRIORITY` | 优先级不在 1–10 |
| `INVALID_TASK_TYPE` | 任务类型不是 SYNC/ASYNC/SCHEDULED |
| `TASK_NOT_FOUND` | task_id 不存在 |
| `INVALID_DEPENDENCY_TYPE` | 依赖类型非法 |

---

## 4. 数据存储

使用模块级 dict（内存）：

```python
# src/sandbox_app/store.py
_tasks: dict[str, Task] = {}
```

保持 minimal diff——不引入数据库、不引入外部依赖、不引入 secrets。

---

## 5. 测试计划（`tests/test_task.py`）

| 测试 | 对应 AC | 描述 |
|------|---------|------|
| `test_create_sync_task` | AC-1 | 创建 SYNC 任务，校验 task_id 和 INITIALIZED |
| `test_create_async_task` | AC-1 | 创建 ASYNC 任务，附带 input_schema |
| `test_create_scheduled_task_with_cron` | AC-1, AC-2 | SCHEDULED + 合法 Cron → 成功 |
| `test_invalid_cron_rejected` | AC-2 | 非法 Cron 表达式 → INVALID_CRON |
| `test_event_trigger` | AC-2 | EVENT 类型触发器 → 正确存储 |
| `test_priority_default_and_boundary` | AC-3 | 默认=5；1 和 10 边界有效 |
| `test_priority_update` | AC-3 | 更新优先级 API 生效 |
| `test_priority_out_of_range_rejected` | AC-3 | 0 和 11 → INVALID_PRIORITY |
| `test_sequential_dependency` | AC-4 | SEQUENTIAL + depends_on 列表 |
| `test_and_parallel_dependency` | AC-4 | AND_PARALLEL 依赖 |
| `test_or_parallel_dependency` | AC-4 | OR_PARALLEL 依赖 |
| `test_circular_dependency_detected` | AC-4 | A→B→A → CIRCULAR_TASK_DEPENDENCY |
| `test_complex_circular_chain` | AC-4 | A→B→C→A 三节点环 |

### 测试覆盖率目标

- 所有 AC 覆盖（AC-5）。
- 边界：优先级 1, 5, 10；非法 0, 11, -1。
- Cron：合法 5 字段、非法 4 字段、非法 6 字段、非法字符。
- 依赖：无依赖、单依赖、多依赖、自依赖（A→A）、直接环、间接环。

---

## 6. 实现步骤（按顺序）

### Step 1: 定义数据模型
- 新建 `src/sandbox_app/task.py`：`Task` dataclass + 状态机常量
- 新建 `src/sandbox_app/trigger.py`：`CronTrigger`, `EventTrigger` + `CRON_PATTERN`
- 新建 `src/sandbox_app/dependency.py`：`DependencyGraph` + 循环检测

### Step 2: 实现存储与 API
- 新建 `src/sandbox_app/store.py`：内存存储 + CRUD
- 新建 `src/sandbox_app/api.py`：暴露 `create_task`, `update_priority`, `set_dependency`, `get_task`

### Step 3: 导出包
- 更新 `src/sandbox_app/__init__.py`：导出新模块的公共 API

### Step 4: 编写测试
- 新建 `tests/test_task.py`：全部测试用例（见上表）

### Step 5: 验证
```bash
pip install -e ".[dev]"
pytest -v tests/test_task.py
ruff check .
```

---

## 7. 文件变更清单

| 操作 | 文件 |
|------|------|
| NEW | `src/sandbox_app/task.py` |
| NEW | `src/sandbox_app/trigger.py` |
| NEW | `src/sandbox_app/dependency.py` |
| NEW | `src/sandbox_app/store.py` |
| NEW | `src/sandbox_app/api.py` |
| EDIT | `src/sandbox_app/__init__.py` |
| NEW | `tests/test_task.py` |

总计：**6 新文件 + 1 编辑**。零新增外部依赖，零 secrets，零数据库。

---

## 8. 关键设计决策

1. **纯内存存储**：对齐 "no secrets" 和 "minimal diff" constraints。未来可替换为 SQLite/Postgres，但当前存根期的运行时隔离不需要持久化。
2. **dataclass 而非 Pydantic**：不引入额外依赖。字段校验在 API 层以显式 if/raise 完成。
3. **5 位 Cron（标准）**：分 时 日 月 星期。与 `croniter` 库兼容但不引入它——仅做格式校验，不解析调度时间。
4. **循环依赖检测采用 DFS**：每次 `set_dependency` 调用时构建邻接表做 DFS，时间复杂度 O(V+E)，在任务量级（预期 < 1000）下足够。
