# T-005: 注册中心心跳与依赖/兼容性校验 — Implementation Plan

## 1. 现状分析

| 项 | 值 |
|---|---|
| 语言/运行时 | Python 3.11+ |
| 构建 | setuptools (`pyproject.toml`) |
| 测试 | pytest (src layout, `pythonpath = ["src"]`) |
| Lint | ruff (line-length=100, py311 target) |
| CI | GitHub Actions: ruff check → pytest -q |
| 现有代码 | `src/sandbox_app/core.py` — `health()` + `ping()` 两个 trivial 函数 |
| 现有测试 | `tests/test_core.py` — 两个 assert 单测 |
| 依赖 | 零运行时依赖 (`dependencies = []`) |

**关键约束**: minimal diff（最小 diff 改动）、每个 AC 有自动化测试、无 secrets。

---

## 2. 模块拆分

新增两个模块，保持现有 `core.py`（health/ping）不动：

```
src/sandbox_app/
├── __init__.py              # 扩增导出
├── core.py                  # 不动
├── registry.py              # NEW: 实例注册/心跳/注销 + 依赖声明
└── compatibility.py         # NEW: 兼容性检查 + 依赖解析状态

tests/
├── test_core.py             # 不动
├── test_registry.py         # NEW: AC-1, AC-2, AC-4 测试
└── test_compatibility.py    # NEW: AC-3 测试
```

---

## 3. 详细设计 — `registry.py`

### 3.1 数据模型

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional
import time as _time


class InstanceStatus(Enum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DEREGISTERED = "DEREGISTERED"


class DependencyType(Enum):
    SERVICE = "SERVICE"
    AGENT = "AGENT"
    PLUGIN = "PLUGIN"


class ResolutionState(Enum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class Dependency:
    dep_type: DependencyType
    name: str
    version_constraint: str  # e.g. ">=1.0", "==2.1.3"


@dataclass
class Instance:
    id: str
    name: str
    type: str                      # "SERVICE" | "AGENT" | "PLUGIN"
    version: str
    depends_on: list[Dependency] = field(default_factory=list)
    status: InstanceStatus = InstanceStatus.HEALTHY
    last_heartbeat: float = field(default_factory=lambda: _time.monotonic())
    consecutive_failures: int = 0
```

### 3.2 Registry 类 — 可注入时钟

```python
@dataclass
class RegistryConfig:
    heartbeat_timeout: float = 30.0    # 秒：超过此阈值 → UNHEALTHY
    max_consecutive_failures: int = 3  # 连续超时 N 次 → DEREGISTERED


class Registry:
    def __init__(
        self,
        config: RegistryConfig | None = None,
        clock: Callable[[], float] | None = None,  # ← 可注入时钟（测试用）
    ) -> None:
        self.config = config or RegistryConfig()
        self._clock = clock or _time.monotonic
        self._instances: dict[str, Instance] = {}
```

### 3.3 API 方法

| 方法签名 | 职责 | AC |
|---|---|---|
| `register(instance: Instance) -> None` | 注册新实例（去重/幂等），入表 | AC-1 |
| `heartbeat(instance_id: str) -> bool` | 刷新 `last_heartbeat`，重置 `consecutive_failures`，返回 True（存在时），不存在返回 False | AC-1 |
| `deregister(instance_id: str) -> None` | 移除实例，或标记 DEREGISTERED（幂等） | AC-1 |
| `add_dependency(instance_id: str, dep: Dependency) -> None` | 给实例追加依赖声明 | AC-2 |
| `check_circular(instance_id: str) -> list[str] | None` | BFS/DFS 检测简单循环依赖；返回环路路径或 None。结果含 `CIRCULAR_DEPENDENCY` 标记 | AC-2 |
| `resolve_dependencies(instance_id: str) -> ResolutionState` | 检查所有直接/间接依赖是否在注册表中且版本满足；激活前调用 | AC-4 |
| `check_health() -> dict[str, list[Instance]]` | 遍历实例，按当前时间检查心跳：超时 → UNHEALTHY；连续超时超阈值 → DEREGISTERED；返回 `{healthy, unhealthy, deregistered}` 分组 | AC-1 |

### 3.4 心跳超时逻辑（核心流程）

```
heartbeat_timeout = 30s, max_consecutive_failures = 3

check_health():
   now = clock()
   for each instance:
     elapsed = now - instance.last_heartbeat
     if elapsed > heartbeat_timeout:
       instance.consecutive_failures += 1
       instance.status = UNHEALTHY
       if instance.consecutive_failures >= max_consecutive_failures:
         instance.status = DEREGISTERED (或直接移除)
     else:
       instance.status = HEALTHY
       instance.consecutive_failures = 0
```

### 3.5 循环依赖检测

```
check_circular(instance_id):
  BFS from instance_id, follow depends_on edges
  For each neighbor:
    if neighbor depends_on instance_id (back-edge): CIRCULAR_DEPENDENCY
    → return [path...]
  Also detect indirect cycles (A → B → C → A) via DFS visited set
  → return cycle path or None
```

### 3.6 依赖解析（激活前）

```
resolve_dependencies(instance_id):
  transitive closure of depends_on
  for each dep:
    dep_instance = registry.get(dep.name)
    if not dep_instance: return UNRESOLVED
    if not version_satisfies(dep_instance.version, dep.version_constraint): return UNRESOLVED
  return RESOLVED
```

版本约束解析：支持 `>=`, `<=`, `==`, `>`, `<`, `!=`。极简实现（parser-free）：
- 用正则 `^(>=|<=|==|>|<|!=)(.+)$` 匹配前缀
- 用 `packaging.version.Version` 或手写 `tuple(int(x) for x in v.split("."))` 比较

---

## 4. 详细设计 — `compatibility.py`

### 4.1 数据模型

```python
class CompatibilityResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"

@dataclass
class IncompatibleItem:
    instance_id: str
    dep_name: str
    required_version: str
    actual_version: str | None
    reason: str  # "missing_dependency" | "version_mismatch" | "circular_dependency" | "unhealthy"

@dataclass
class CompatibilityReport:
    result: CompatibilityResult
    incompatible_items: list[IncompatibleItem] = field(default_factory=list)
    checked_instance_id: str = ""
    timestamp: float = field(default_factory=lambda: _time.monotonic())
```

### 4.2 API

```python
def check_compatibility(instance_id: str, registry: Registry) -> CompatibilityReport:
```

逻辑：
1. 检查实例是否存在
2. 检查实例状态（UNHEALTHY → WARNING）
3. 检查循环依赖（有环路 → FAIL + CIRCULAR_DEPENDENCY item）
4. 对所有 depends_on 逐一检查：
   - 依赖不存在 → FAIL
   - 依赖版本不匹配 → FAIL 或 WARNING（视约束刚性）
   - 全部通过 → PASS
5. 返回 `CompatibilityReport`（result + incompatible_items）

---

## 5. 测试计划

### 5.1 `tests/test_registry.py` (AC-1, AC-2, AC-4)

| 测试 | 覆盖 |
|---|---|
| `test_register_instance` | 注册一个实例，断言在注册表中可查 |
| `test_heartbeat_updates_timestamp` | heartbeat 后 last_heartbeat 更新，consecutive_failures 归零 |
| `test_heartbeat_nonexistent_returns_false` | 不存在的实例 ID 返回 False |
| `test_deregister_removes_instance` | 注销后 get 返回 None |
| `test_health_check_marks_unhealthy_on_timeout` | **注入假时钟**：注册 → 心跳正常 → 推进时间过 timeout → check_health 标记 UNHEALTHY（AC-5 核心） |
| `test_health_check_deregisters_after_consecutive_failures` | **注入假时钟**：连续 N 次超时 → 自动注销（AC-5） |
| `test_add_dependency` | 添加依赖声明后实例 depends_on 包含该依赖 |
| `test_circular_dependency_direct` | A depends_on B, B depends_on A → check_circular(A) 返回环路 |
| `test_circular_dependency_indirect` | A→B, B→C, C→A → check_circular(A) 返回 3-step 环路 |
| `test_no_circular_dependency` | 合法 DAG：A→B, A→C → check_circular(A) 返回 None |
| `test_resolve_dependencies_all_resolved` | 依赖全部在注册表中且版本匹配 → RESOLVED |
| `test_resolve_dependencies_missing_dep` | 依赖不在注册表 → UNRESOLVED |
| `test_resolve_dependencies_version_mismatch` | 依赖版本不满足约束 → UNRESOLVED |
| `test_resolve_dependencies_transitive` | 间接依赖（B→C）也满足时 → RESOLVED |

### 5.2 `tests/test_compatibility.py` (AC-3)

| 测试 | 覆盖 |
|---|---|
| `test_compatibility_pass` | 所有依赖满足 → PASS，incompatible_items 为空 |
| `test_compatibility_fail_missing_dep` | 依赖不在注册表 → FAIL，item 含 missing_dependency |
| `test_compatibility_fail_circular` | 有循环依赖 → FAIL，reason=circular_dependency |
| `test_compatibility_warning_unhealthy` | 实例 UNHEALTHY → 至少 WARNING |
| `test_compatibility_result_structure` | 断言 report 包含 result、incompatible_items、checked_instance_id、timestamp（AC-5 结构校验） |
| `test_compatibility_multiple_incompatible_items` | 两个依赖同时失败 → incompatible_items 长度=2 |

---

## 6. 时钟注入模式

```python
class FakeClock:
    """测试用可控时钟。"""
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds
```

Registry 构造接受 `clock: Callable[[], float]`，默认 `time.monotonic`。
测试中传入 `FakeClock()` 即可精确控制时间推进，验证心跳超时逻辑。

---

## 7. 版本约束解析（最小实现）

```python
import re

_VCOMP_RE = re.compile(r"^(>=|<=|==|>|<|!=)(.+)$")

def version_satisfies(actual: str, constraint: str) -> bool:
    m = _VCOMP_RE.match(constraint)
    if not m:
        raise ValueError(f"Invalid version constraint: {constraint}")
    op, target = m.group(1), m.group(2)
    a = _parse_version(actual)
    t = _parse_version(target)
    return {
        ">=": lambda: a >= t,
        "<=": lambda: a <= t,
        "==": lambda: a == t,
        ">":  lambda: a > t,
        "<":  lambda: a < t,
        "!=": lambda: a != t,
    }[op]()

def _parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))
```

---

## 8. `__init__.py` 更新

```python
from .core import health, ping
from .registry import (
    Registry, RegistryConfig, Instance, InstanceStatus, Dependency, DependencyType, ResolutionState,
    check_health, version_satisfies,
)
from .compatibility import CompatibilityReport, CompatibilityResult, IncompatibleItem, check_compatibility

__all__ = [
    "health", "ping",
    "Registry", "RegistryConfig", "Instance", "InstanceStatus", "Dependency", "DependencyType",
    "ResolutionState",
    "CompatibilityReport", "CompatibilityResult", "IncompatibleItem", "check_compatibility",
    "version_satisfies",
]
```

---

## 9. 文件变更清单

| 文件 | 操作 | 行数估算 |
|---|---|---|
| `src/sandbox_app/core.py` | 不修改 | 0 |
| `src/sandbox_app/registry.py` | **新建** | ~180 行 |
| `src/sandbox_app/compatibility.py` | **新建** | ~60 行 |
| `src/sandbox_app/__init__.py` | 修改（扩增导出） | +15 行 |
| `tests/test_registry.py` | **新建** | ~160 行 |
| `tests/test_compatibility.py` | **新建** | ~80 行 |
| `tests/test_core.py` | 不修改 | 0 |
| `pyproject.toml` | 不修改 | 0 |
| `.github/workflows/ci.yml` | 不修改 | 0 |

**总 diff**: ~500 行新代码，零对现有代码的破坏性改动。

---

## 10. 风险与权衡

| 风险 | 缓解 |
|---|---|
| 循环检测仅覆盖注册表内声明的依赖，不检测外部未注册依赖 | 设计范围内；AC-2 明确"简单循环依赖" |
| 版本约束仅支持简单比较符，不支持 `~=`、`^` 等复杂语义 | minimal diff 约束下合理；`>=`, `<=`, `==`, `>`, `<`, `!=` 覆盖核心场景 |
| 注册表纯内存实现，无持久化 | AC 未要求持久化；内存注册表明确定义在 AC-3 |

---

## 11. 实现顺序

```
1. registry.py          → 数据模型 + Registry 类 + 心跳/注册/注销/依赖 API + version_satisfies
2. compatibility.py     → CompatibilityReport + check_compatibility（依赖 registry）
3. tests/test_registry.py      → 先写测试（AC-1, AC-2, AC-4, AC-5）
4. tests/test_compatibility.py → 后写测试（AC-3）
5. __init__.py          → 扩增导出
6. pytest + ruff check  → 验证通过
```

---

## 12. PR 描述

```
feat(registry): 注册中心心跳与依赖/兼容性校验 (T-005)

- AC-1: 实例注册/心跳/注销 API + 可注入时钟 + 超时 UNHEALTHY / 连续失败注销
- AC-2: 依赖声明 API（SERVICE/AGENT/PLUGIN + version_constraint）+ BFS 循环检测
- AC-3: 兼容性检查 API 返回 PASS/FAIL/WARNING 含 incompatible_items
- AC-4: 激活前依赖解析 RESOLVED/UNRESOLVED
- AC-5: 自动化测试覆盖心跳超时逻辑、循环依赖、检查结果结构
```
