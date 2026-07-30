# T-016 可观测、审计与权限基线 — 实现计划

## 概述

在现有 `sandbox_app` Python 骨架基础上，以**最小 diff** 新增 8 项能力：结构化日志、Trace/Span 查询、告警规则 CRUD、监控汇总、操作审计、合规策略、RBAC 判定、敏感字段脱敏。全部**纯内存存储**（无外部依赖），每项 AC 带对应自动化测试。

## 仓库快照（基线）

- **语言**: Python 3.11+
- **包管理**: setuptools + pyproject.toml
- **源码目录**: `src/sandbox_app/`
- **测试目录**: `tests/`
- **CI**: GitHub Actions（lint + pytest）
- **现有源码**: `core.py`（`health()`, `ping()`）、`__init__.py`（导出）
- **现有测试**: `test_core.py`（`test_health`, `test_ping`）
- **lint**: ruff（line-length=100）

## 文件变更清单

| 操作 | 文件 | 用途 |
|------|------|------|
| 新增 | `src/sandbox_app/logging.py` | 结构化日志写入/查询 + Trace/Span |
| 新增 | `src/sandbox_app/alerting.py` | 告警规则 CRUD |
| 新增 | `src/sandbox_app/monitoring.py` | 监控汇总 API |
| 新增 | `src/sandbox_app/audit.py` | 操作审计追加/查询（不可变） |
| 新增 | `src/sandbox_app/compliance.py` | 合规策略配置存储 |
| 新增 | `src/sandbox_app/rbac.py` | RBAC 策略判定函数 |
| 新增 | `src/sandbox_app/masking.py` | 敏感字段脱敏工具 |
| 修改 | `src/sandbox_app/__init__.py` | 导出新模块公共接口 |
| 新增 | `tests/test_logging.py` | AC-1 (log) + AC-2 (trace) 测试 |
| 新增 | `tests/test_alerting.py` | AC-3 告警 CRUD 测试 |
| 新增 | `tests/test_monitoring.py` | AC-4 监控汇总测试 |
| 新增 | `tests/test_audit.py` | AC-5 审计追加/查询测试 |
| 新增 | `tests/test_compliance.py` | AC-6 合规策略测试 |
| 新增 | `tests/test_rbac.py` | AC-7 RBAC 判定测试 |
| 新增 | `tests/test_masking.py` | AC-8 脱敏单元测试 |

## 逐 AC 详细计划

### AC-1: 结构化日志写入与查询

**文件**: `src/sandbox_app/logging.py`

**数据结构**:
```python
LogEntry = TypedDict  # timestamp, level, message, agent_id, trace_id (可选)
```

**API**:
- `write_log(level, message, agent_id=None, trace_id=None, timestamp=None) -> LogEntry` — 追加到内存 list
- `query_logs(start_time, end_time, level=None, agent_id=None) -> list[LogEntry] | ErrorDict`
  - 若 `end_time - start_time > 24h` → 返回 `{"error": "LOG_TIME_RANGE_EXCEEDED", "max_hours": 24}`
- `clear_logs()` — 仅测试用

**测试用例** (`tests/test_logging.py`):
1. 写入一条日志，查询返回该条
2. 按 level 过滤
3. 按 agent_id 过滤
4. 时间窗 > 24h 返回 LOG_TIME_RANGE_EXCEEDED
5. 空结果返回空列表

---

### AC-2: Trace/Span 查询 API

**文件**: `src/sandbox_app/logging.py`（同文件，相关性高）

**数据结构**:
```python
Span = TypedDict  # span_id, trace_id, parent_span_id, operation, start_time, end_time, status
```

**API**:
- `put_span(trace_id, span_id, operation, parent_span_id=None, ...) -> Span`
- `get_trace_tree(trace_id) -> TraceTree | Error404` — 返回该 trace 的 span 树或 `{"error": "NOT_FOUND", "detail": "Trace <id> not found"}`
- `get_spans(trace_id) -> list[Span] | Error404` — 返回该 trace 的 span 列表或 404
- `clear_traces()` — 仅测试用

**`trace_tree` 返回格式**:
```python
{
    "trace_id": "...",
    "root": {  # 第一个 parent_span_id is None 的 span
        "span": {...},
        "children": [...]
    }
}
```

**测试用例** (`tests/test_logging.py`):
1. 查询不存在的 trace → 返回 error 字典（模拟 404）
2. 写入 3 个 span，查询该 trace → 返回完整列表
3. 构造父子 span 树，`get_trace_tree` 返回正确嵌套结构
4. 空 trace（无 span）→ 404

---

### AC-3: 告警规则 CRUD

**文件**: `src/sandbox_app/alerting.py`

**数据结构**:
```python
AlertRule = TypedDict  # id, metric, condition, severity, notification_channels, enabled
```

**API**:
- `create_rule(metric, condition, severity, notification_channels) -> AlertRule`
- `get_rule(rule_id) -> AlertRule | None`
- `list_rules() -> list[AlertRule]`
- `update_rule(rule_id, **fields) -> AlertRule | None`
- `delete_rule(rule_id) -> bool`
- `clear_rules()` — 仅测试用

**测试用例** (`tests/test_alerting.py`):
1. CRUD 完整闭环：创建 → 查询 → 更新 → 删除
2. 列出所有规则
3. 删除不存在的规则返回 False
4. 更新不存在的规则返回 None
5. 按严重级别过滤

---

### AC-4: 监控汇总 API

**文件**: `src/sandbox_app/monitoring.py`

**数据结构**:
```python
Metrics = TypedDict  # log_count, trace_count, alert_count, error_count (计数器桩)
```

**API**:
- `get_global_status() -> dict` — 返回 `{"global_status": "healthy"|"degraded"|"down", "metrics": {...}, "uptime_seconds": ...}`
- `increment_counter(name)` / `get_counters() -> Metrics` — 可用的计数器桩

**测试用例** (`tests/test_monitoring.py`):
1. `get_global_status()` 返回 `global_status` 字段和 `metrics` 字典
2. 计数器 increment + get 验证
3. 初始状态为 healthy

---

### AC-5: 操作审计追加与查询

**文件**: `src/sandbox_app/audit.py`

**核心约束**: **不可变追加** — 同一 `key` 写入两次应拒绝覆盖。

**数据结构**:
```python
AuditEntry = TypedDict  # audit_id, key, action, subject, resource, timestamp, metadata
```

**API**:
- `append_audit(key, action, subject, resource, metadata=None) -> AuditEntry | ErrorDict`
  - 若 `key` 已存在 → 返回 `{"error": "DUPLICATE_KEY", "detail": "Audit entry with key '<key>' already exists. Audit is append-only."}`
- `query_audit(subject=None, resource=None, action=None, start_time=None, end_time=None) -> list[AuditEntry]`
- `clear_audit()` — 仅测试用

**测试用例** (`tests/test_audit.py`):
1. 追加一条审计，查询返回该条
2. 同一 key 再次追加 → 返回 DUPLICATE_KEY 错误
3. 按 subject 过滤
4. 按 resource 过滤
5. 按时间窗过滤
6. 多字段组合过滤

---

### AC-6: 合规策略配置存储

**文件**: `src/sandbox_app/compliance.py`

**子集**: RETENTION（保留策略）、MASKING（脱敏策略）

**数据结构**:
```python
CompliancePolicy = TypedDict  # policy_id, policy_type ("retention"|"masking"), config, enabled
```

**API**:
- `set_policy(policy_id, policy_type, config) -> CompliancePolicy`
- `get_policy(policy_id) -> CompliancePolicy | None`
- `list_policies(policy_type=None) -> list[CompliancePolicy]`
- `delete_policy(policy_id) -> bool`
- `clear_policies()` — 仅测试用

**内置默认**:
- `retention.default`: `{"max_log_age_days": 90, "max_audit_age_days": 365}`
- `masking.default`: `{"fields": ["password", "token", "secret", "api_key"]}`

**测试用例** (`tests/test_compliance.py`):
1. 设置 RETENTION 策略并回读
2. 设置 MASKING 策略并回读
3. 列出所有策略
4. 按 type 过滤列出
5. 删除策略
6. 设置已有策略覆盖旧值

---

### AC-7: RBAC 策略判定

**文件**: `src/sandbox_app/rbac.py`

**模型**: ALLOW/DENY 策略，subjects/resources/actions 三元组判定。

**数据结构**:
```python
Policy = TypedDict  # id, effect ("ALLOW"|"DENY"), subjects, resources, actions
```

**判定规则**: DENY 优先（任一 DENY 匹配 → 拒绝），否则需要至少一个 ALLOW 匹配。

**API**:
- `add_policy(effect, subjects, resources, actions) -> Policy`
- `check_permission(subject, resource, action) -> bool`
  - 返回 True（允许）或 False（拒绝）
- `remove_policy(policy_id) -> bool`
- `clear_policies()` — 仅测试用

**匹配逻辑**: 支持通配符 `"*"` 匹配任意值。

**测试用例** (`tests/test_rbac.py`):
1. 精确 ALLOW 匹配 → True
2. 通配符 `"*"` 匹配 → True
3. 无匹配策略 → False（默认拒绝）
4. DENY 覆盖 ALLOW（DENY 优先）
5. 多个 subject 匹配其中之一
6. 移除策略后判定变化

---

### AC-8: 敏感字段脱敏

**文件**: `src/sandbox_app/masking.py`

**函数**:
- `mask_value(value: str, keep_chars: int = 4) -> str`
  - `"my-secret-token"` → `"my-s**********"`
  - 暴露前 `keep_chars` 个字符，其余替换为 `*`
  - 若 value 长度 ≤ keep_chars → 全量返回（不脱敏）
- `mask_dict(data: dict, sensitive_fields: list[str] | None = None) -> dict`
  - 递归遍历 dict，对匹配的 key 调用 `mask_value`
  - 默认 sensitive_fields: `["password", "token", "secret", "api_key", "authorization"]`
  - 支持嵌套 dict 和 list[dict]
- `mask_sensitive(data: dict) -> dict`
  - 便捷函数，使用默认敏感字段列表

**测试用例** (`tests/test_masking.py`):
1. `mask_value("my-password-here", 4)` → `"my-p**********"`
2. `mask_value("abc", 4)` → `"abc"`（短值不脱敏）
3. `mask_value("abc", 2)` → `"ab*"`
4. `mask_dict` 脱敏嵌套 dict 中的 password 和 token
5. `mask_dict` 递归处理嵌套 list
6. `mask_sensitive` 使用默认字段列表
7. 自定义 sensitive_fields 覆盖

---

## 实现顺序

```
Phase 1 (独立, 可并行):
  ├── AC-8: masking.py + test_masking.py    ← 最简单，零依赖
  ├── AC-7: rbac.py + test_rbac.py          ← 纯函数判定
  └── AC-6: compliance.py + test_compliance.py ← 简单 CRUD 存储

Phase 2 (独立, 可并行):
  ├── AC-5: audit.py + test_audit.py        ← 追加约束
  └── AC-3: alerting.py + test_alerting.py  ← CRUD 带过滤

Phase 3:
  ├── AC-1: logging.py 结构化日志            ← 带时间窗校验
  └── AC-2: logging.py Trace/Span           ← 同文件追加

Phase 4:
  └── AC-4: monitoring.py + test_monitoring.py ← 依赖 logging 计数器

Phase 5:
  └── __init__.py 导出整合
```

## 约束检查

| 约束 | 满足方式 |
|------|----------|
| **minimal diff** | 不修改 `core.py`、`pyproject.toml`、`ci.yml`；仅在 `__init__.py` 新增导出行 |
| **automated tests** | 每个新增 .py 对应一个 test 文件，共 7 个新测试文件 |
| **no secrets** | 全部内存存储，无密钥/凭据硬编码 |
| **无外部依赖** | 纯标准库 + typing，不新增 pip 依赖 |

## 关键设计决策

1. **内存存储** — 使用模块级 `list[dict]` / `dict[str, dict]`，不引入数据库。每个模块提供 `clear_*()` 函数供测试隔离。
2. **"404" 模拟** — 本项目无 HTTP 框架，"404" 用返回值 `{"error": "NOT_FOUND", ...}` 模拟，测试验证字典结构。
3. **TypedDict** — 用 `typing.TypedDict` 描述数据结构，既是文档也是类型检查锚点。
4. **DENY 优先** — RBAC 判定中 DENY 策略优先于 ALLOW，符合最小权限安全原则。
5. **不可变审计** — 以 `key` 为唯一标识，重复 key 拒绝写入，保证审计链完整性。
