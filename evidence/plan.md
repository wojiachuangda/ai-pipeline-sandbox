# 工作流 DSL 模型与 CRUD/版本/模板 — 实施计划

**任务**: T-010 | **日期**: 2026-07-30 | **仓库**: AI Pipeline Sandbox (Python 3.11+)

---

## 1. 现状分析

当前代码库是一个最小 Python 沙盒项目：

| 文件 | 内容 |
|---|---|
| `src/sandbox_app/core.py` | `health()`, `ping()` 两个函数 |
| `src/sandbox_app/__init__.py` | 导出 `health`, `ping` |
| `tests/test_core.py` | 两个 trivially 测试 |
| `pyproject.toml` | setuptools, pytest, ruff |
| `.github/workflows/ci.yml` | lint + test |

无 Web 框架、无数据库、无 ORM。约束 **minimal diff**，因此所有新增代码均放置在新包 `src/sandbox_app/workflow/` 中，不引入外部依赖（仅使用标准库 + 项目已有的 pytest/ruff）。

---

## 2. 架构决策

### 2.1 不引入数据库
使用进程内 `dict` 存储（内存仓库模式），Workflow/Version/Template 各有独立 store。这满足 CRUD 语义且零依赖。

### 2.2 不引入 Web 框架
AC 中 "API+JSON DSL" 指 Python 模块 API（函数签名）+ JSON 格式的 DSL 定义。不做 HTTP 端点——纯 Python API。

### 2.3 Pydantic 选型
当前项目无 Pydantic。为保持 minimal diff，DSL 校验用 dataclass + 手写 `__post_init__` 实现——不新增 Pydantic 依赖。

### 2.4 目录结构（新增文件）

```
src/sandbox_app/
  workflow/
    __init__.py        # 公开 API 导出
    dsl.py             # DSL 节点/边/图的 dataclass 定义 & 校验
    models.py          # Workflow / WorkflowVersion / WorkflowTemplate 领域模型 + 内存仓库
    service.py         # CRUD 编排、环检测、版本回滚、模板管理
    errors.py          # 错误码 & 异常类型
tests/
  test_workflow.py     # 全覆盖自动化测试
```

---

## 3. DSL 最小约定 (PRD-GAP-DSL)

### 3.1 Workflow DSL JSON 结构

```json
{
  "nodes": [
    {"id": "n1", "type": "start"},
    {"id": "n2", "type": "task", "label": "处理步骤"},
    {"id": "n3", "type": "end"}
  ],
  "edges": [
    {"source": "n1", "target": "n2"},
    {"source": "n2", "target": "n3"}
  ]
}
```

### 3.2 Node 类型

| type | 说明 | 允许作为环的豁免 |
|---|---|---|
| `start` | 入口节点（必有、唯一） | 否 |
| `end` | 出口节点（至少一个） | 否 |
| `task` | 普通任务节点 | 否 |
| `decision` | 条件分支节点 | 否 |
| `loop` | 循环控制节点 | **是** — 允许自环/回边 |

### 3.3 校验规则

| 规则 | 触发错误 |
|---|---|
| `nodes` 非空且至少 1 个 | `INVALID_WORKFLOW_DSL` |
| 存在且仅一个 `type: start` | `INVALID_WORKFLOW_DSL` |
| 至少有一个 `type: end` | `INVALID_WORKFLOW_DSL` |
| `edges` 中的 `source`/`target` 必须引用已声明的节点 ID | `INVALID_WORKFLOW_DSL` |
| 图中存在环且无 `loop` 类型节点 | `CIRCULAR_WORKFLOW` |

---

## 4. 模块设计

### 4.1 `workflow/errors.py` — 错误定义

```python
class WorkflowError(Exception): ...
class InvalidWorkflowDslError(WorkflowError): ...   # INVALID_WORKFLOW_DSL
class CircularWorkflowError(WorkflowError): ...     # CIRCULAR_WORKFLOW
class WorkflowNotFoundError(WorkflowError): ...
class VersionNotFoundError(WorkflowError): ...
class TemplateNotFoundError(WorkflowError): ...
```

### 4.2 `workflow/dsl.py` — DSL 模型

- `NodeDef` dataclass: `id`, `type`, `label`（可选）
- `EdgeDef` dataclass: `source`, `target`
- `WorkflowDsl` dataclass: `nodes`, `edges` + `validate()` 方法
  - 从 dict/JSON 解析 (`from_dict`)
  - 校验节点非空、start/end 规则、边引用完整性
  - 返回规范化错误信息
- `CycleDetector` 函数: DFS 拓扑检测
  - 先找出所有 `loop` 类型节点 ID → 豁免集合
  - 构建邻接表时，若边指向豁免节点则跳过该边
  - 对剩余图做 DFS 三色标记法环检测
  - 有环 → 抛出 `CircularWorkflowError`

### 4.3 `workflow/models.py` — 领域模型 & 内存仓库

**Workflow**:
- `id` (UUID), `name`, `description`, `dsl` (WorkflowDsl), `created_at`, `updated_at`, `current_version`
- `WorkflowRepository`: `create()`, `get()`, `list()`, `update()`

**WorkflowVersion** (对齐 Agent 版本语义子集):
- `id`, `workflow_id`, `version_number` (整数递增), `dsl` (快照), `created_at`, `label`
- `WorkflowVersionRepository`: `create_version()`, `list_versions()`, `get_version()`

**WorkflowTemplate**:
- `id`, `name`, `description`, `dsl`, `visibility` (`PRIVATE` | `TENANT`), `created_at`
- `WorkflowTemplateRepository`: `save_template()`, `get_template()`, `list_templates()`

### 4.4 `workflow/service.py` — 业务逻辑

| 函数 | 功能 | AC |
|---|---|---|
| `create_workflow(dsl_dict, name, description)` | 解析 DSL、校验、创建 Workflow + 初始版本 v1 | AC-1 |
| `get_workflow(workflow_id)` | 按 ID 获取 | AC-1 |
| `list_workflows()` | 列出全部 | AC-1 |
| `update_workflow(workflow_id, dsl_dict)` | 校验 + 更新 DSL + 创建新版本 | AC-1, AC-3 |
| `create_workflow_version(workflow_id, label)` | 基于当前 DSL 创建命名版本 | AC-3 |
| `list_workflow_versions(workflow_id)` | 列出版本历史 | AC-3 |
| `rollback_workflow(workflow_id, version_number)` | 回滚到指定版本（更新 current DSL = 版本快照） | AC-3 |
| `save_as_template(workflow_id, template_name, visibility)` | 从工作流保存为 PRIVATE/TENANT 模板 | AC-4 |
| `list_templates(visibility_filter)` | 列出模板 | AC-4 |

### 4.5 `workflow/__init__.py` — 公开 API

导出所有公开函数、类和异常。

---

## 5. 环检测算法

```
输入: nodes (list[NodeDef]), edges (list[EdgeDef])
1. 收集所有 type="loop" 的节点 ID → exempt_ids
2. 构建邻接表: for edge in edges:
     if edge.target in exempt_ids → 跳过 (循环控制节点允许回边)
     否则 adj[edge.source].append(edge.target)
3. DFS 三色标记:
     WHITE=0, GRAY=1, BLACK=2
     对所有未访问节点做 dfs(v):
       标记为 GRAY
       for neighbor in adj[v]:
         if color[neighbor] == GRAY → 发现环 → CIRCULAR_WORKFLOW
         if color[neighbor] == WHITE → dfs(neighbor)
       标记为 BLACK
4. 无环 → 通过
```

时间 O(V+E)，空间 O(V)。

---

## 6. 文件清单 & 预估行数

| 文件 | 功能 | 预估行数 |
|---|---|---|
| `src/sandbox_app/workflow/__init__.py` | API 导出 | ~12 |
| `src/sandbox_app/workflow/errors.py` | 异常类型 | ~25 |
| `src/sandbox_app/workflow/dsl.py` | DSL 模型 + 校验 + 环检测 | ~120 |
| `src/sandbox_app/workflow/models.py` | 领域模型 + 内存仓库 | ~130 |
| `src/sandbox_app/workflow/service.py` | 业务逻辑编排 | ~130 |
| `tests/test_workflow.py` | 全覆盖测试 | ~200 |
| `src/sandbox_app/__init__.py` | 更新导出 (追加 workflow 模块) | +3 |

**总计**: ~5 个新文件 + 1 个修改，~620 行新增。

---

## 7. 测试计划

### 7.1 创建/获取/列表 (AC-1)

| 用例 | 预期 |
|---|---|
| 用合法 DSL 创建 → 返回 Workflow | 成功 |
| 用 0 节点 DSL 创建 → `InvalidWorkflowDslError` | INVALID_WORKFLOW_DSL |
| 无 start 节点 → `InvalidWorkflowDslError` | INVALID_WORKFLOW_DSL |
| 无 end 节点 → `InvalidWorkflowDslError` | INVALID_WORKFLOW_DSL |
| edge 引用不存在的节点 → `InvalidWorkflowDslError` | INVALID_WORKFLOW_DSL |
| get_workflow(不存在的ID) → `WorkflowNotFoundError` | 正确 |
| list_workflows 返回全部 | 正确 |

### 7.2 环检测 (AC-2)

| 用例 | 预期 |
|---|---|
| DAG（无环）→ 创建成功 | 成功 |
| 含环且无 loop 节点 → `CircularWorkflowError` | CIRCULAR_WORKFLOW |
| 含环但有 loop 节点（环涉及 loop 节点）→ 创建成功 | 允许 |
| 含环有 loop 节点但环不涉及 loop → `CircularWorkflowError` | 禁止 |

### 7.3 版本管理 (AC-3)

| 用例 | 预期 |
|---|---|
| 创建 workflow 自动生成 v1 | version_number=1 |
| 更新 workflow DSL 自动生成新版本 | v2, DSL 为更新内容 |
| create_workflow_version 带 label | 命名版本 |
| list_versions 返回版本历史 | 按 version_number 排序 |
| rollback 到 v1 | current DSL = v1 快照 |
| rollback 后更新 DSL 再生成新版本 | 版本号正确递增 |
| rollback 到不存在的版本 → `VersionNotFoundError` | 正确 |

### 7.4 模板 (AC-4)

| 用例 | 预期 |
|---|---|
| 保存为 PRIVATE 模板 → | visibility=PRIVATE |
| 保存为 TENANT 模板 → | visibility=TENANT |
| list_templates(PRIVATE) 只返回 PRIVATE | 过滤正确 |
| 用不存在的 workflow_id 保存模板 → `WorkflowNotFoundError` | 正确 |

### 7.5 不测试的内容 (AC-6)

- 无 UI 测试
- 无拖拽交互测试
- 无 HTTP 端点测试

---

## 8. 实施顺序

1. **`errors.py`** — 异常基类（被所有模块引用）
2. **`dsl.py`** — DSL 模型、校验、环检测（纯函数，可独立测试）
3. **`models.py`** — 领域模型 + 仓库（依赖 dsl.py）
4. **`service.py`** — 业务编排（依赖 models.py + dsl.py）
5. **`workflow/__init__.py`** + 更新 **`src/sandbox_app/__init__.py`**
6. **`tests/test_workflow.py`** — 全量测试（可边写边测）
7. 运行 `pytest` + `ruff check` 验证通过
8. 确认 CI 绿色

---

## 9. 约束检查清单

| 约束 | 状态 |
|---|---|
| minimal diff — 仅新增 workflow 包 + 测试 | ✅ |
| 每个 AC 有自动化测试 | ✅ |
| 无 secrets / 密钥 | ✅ |
| 无拖拽 UI | ✅ |
| 不新增外部 pip 依赖 | ✅ |
| 兼容现有 CI (ruff + pytest) | ✅ |
| 不修改 core.py | ✅ |
