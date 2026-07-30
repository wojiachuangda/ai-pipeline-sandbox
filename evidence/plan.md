# T-001 平台骨架与领域模型基线 — 实现计划

> **源：** goal.md §1 / §9 / §10；`docs/goal-split/stubs/T-001.md`  
> **日期：** 2026-07-30  
> **约束：** minimal diff，无 secrets，每个 AC 有自动化测试覆盖

---

## 1. 现状勘察

| 资产 | 路径 | 状态 |
|---|---|---|
| 工程元数据 | `pyproject.toml` | ✅ 已有 setuptools 骨架，项目名 `sandbox-app`，Python ≥3.11 |
| 业务代码 | `src/sandbox_app/` | ⚠️ 仅有 `core.py`（`health()` / `ping()` 纯 dict 函数，无 HTTP） |
| 测试 | `tests/test_core.py` | ⚠️ 2 个测试，仅覆盖 dict 返回值 |
| CI | `.github/workflows/ci.yml` | ✅ lint + pytest |
| README | `README.md` | ⚠️ 存在但未描述新的领域模块边界 |

**关键缺口：** 无领域枚举/模型层，无 HTTP 传输层，无统一错误码结构。

---

## 2. 目标架构

```
src/sandbox_app/
├── __init__.py              # 导出公共符号（不变）
├── core.py                  # health() / ping() 纯逻辑（保留，供http层调用）
├── domain/                  # [NEW] 领域层
│   ├── __init__.py          # 导出 Role, Tenant, ErrorCode
│   └── models.py            # 枚举 + dataclass 定义
└── api/                     # [NEW] HTTP 传输层
    ├── __init__.py          # 导出 app 工厂
    └── health.py            # /live, /ready 端点（Starlette）

tests/
├── test_core.py             # 已有（保留）
├── test_domain.py           # [NEW] 枚举/错误码/Tenant 上下文测试
└── test_health_api.py       # [NEW] HTTP /live + /ready 测试
```

**依赖变化：** 新增运行时依赖 `starlette[standard]`（← 包含 uvicorn，最小 ASGI 框架）。

---

## 3. 逐 AC 实现步骤

### AC-1：可安装包结构 + README 模块边界说明

**文件：**
- `pyproject.toml` — 添加 `starlette` 依赖，更新 description
- `README.md` — 补充 `domain/` 与 `api/` 的模块职责说明

**变更要点：**
- `dependencies = ["starlette[standard]>=0.40"]`
- README 新增「模块」章节，每层一句话说明边界

---

### AC-2：领域枚举与基础模型

**文件：** `src/sandbox_app/domain/models.py`（新建）

```python
# —— 枚举 ——
class Role(str, Enum):
    ADMIN = "admin"
    AGENT = "agent"
    OBSERVER = "observer"

# —— 租户上下文 ——
@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    name: str

# —— 统一错误码 ——
@dataclass(frozen=True)
class ErrorCode:
    code: str
    message: str
```

**文件：** `src/sandbox_app/domain/__init__.py`（新建）— 导出 `Role`, `Tenant`, `ErrorCode`

**设计决策：**
- `Role` 用 `StrEnum`：序列化友好，HTTP body / DB 直接可用
- `Tenant` 用 frozen dataclass：不可变值对象，线程安全
- `ErrorCode` 用 frozen dataclass：code 为机器可读 slug，message 为人可读文案

---

### AC-3：健康检查 HTTP 接口（live / ready）

**文件：** `src/sandbox_app/api/health.py`（新建）

```python
from starlette.applications import Starlette
from starlette.routing import Route

async def live(request):
    return JSONResponse({"status": "ok"})

async def ready(request):
    return JSONResponse({"status": "ready"})

app = Starlette(routes=[
    Route("/live", live),
    Route("/ready", ready),
])
```

**文件：** `src/sandbox_app/api/__init__.py`（新建）— 导出 `app`

**本地运行：**
```bash
uvicorn sandbox_app.api.health:app --port 8000
```

**设计决策：**
- 选择 Starlette（非 FastAPI）：仅为健康端点引入 FastAPI 属于过度工程，T-002+ 可按需升级
- `/live` 表示进程存活，`/ready` 表示可接收流量（后续可加依赖检查）

---

### AC-4：≥3 个单元测试

| 文件 | 覆盖目标 | 测试数 |
|---|---|---|
| `tests/test_domain.py` | Role 枚举值、ErrorCode code/message 结构、Tenant 不可变性 | ≥2 |
| `tests/test_health_api.py` | HTTP GET /live → 200、GET /ready → 200 | ≥2 |
| `tests/test_core.py` | 已有 2 个（保留） | 2 |

**测试工具：** `starlette.testclient.TestClient`（无需启动真实服务器）

**测试文件：** `tests/test_domain.py`

```python
def test_role_enum_values():
    assert Role.ADMIN == "admin"
    assert Role.AGENT == "agent"
    assert Role.OBSERVER == "observer"

def test_error_code_structure():
    err = ErrorCode(code="NOT_FOUND", message="Resource not found")
    assert err.code == "NOT_FOUND"
    assert err.message == "Resource not found"
```

**测试文件：** `tests/test_health_api.py`

```python
from starlette.testclient import TestClient
from sandbox_app.api.health import app

client = TestClient(app)

def test_live_returns_200():
    resp = client.get("/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

def test_ready_returns_200():
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}
```

---

### AC-5：不实现 Agent 业务 API

**验证门禁：** 检查 `api/` 目录下无任何 Agent/Organization/Task 路由文件。  
`grep -r "agent\|Agent\|organization\|task" src/sandbox_app/api/` 应返回空。

---

## 4. 文件变更清单

| 操作 | 文件 |
|---|---|
| ✏️ 编辑 | `pyproject.toml` — 加 starlette 依赖 |
| ✏️ 编辑 | `README.md` — 补充模块边界说明 |
| ✨ 新建 | `src/sandbox_app/domain/__init__.py` |
| ✨ 新建 | `src/sandbox_app/domain/models.py` |
| ✨ 新建 | `src/sandbox_app/api/__init__.py` |
| ✨ 新建 | `src/sandbox_app/api/health.py` |
| ✨ 新建 | `tests/test_domain.py` |
| ✨ 新建 | `tests/test_health_api.py` |
| — 不动 | `src/sandbox_app/core.py`、`tests/test_core.py`、`.github/` |

**统计：** 5 新建 + 2 编辑 + 4 不动 = **最小 diff**。

---

## 5. 风险与替代方案

| 风险 | 缓解 |
|---|---|
| Starlette 太轻，T-002 仍需 FastAPI 迁移 | 接受：AC-5 明确"不实现 Agent API"，迁移成本低（FastAPI 兼容 Starlette） |
| `Tenant` 定义后续需扩展 | 用 frozen dataclass 保持初始定义小，后续加字段不破坏现有测试 |

## 6. 验收检查

```bash
pip install -e ".[dev]"
pytest -q                    # ≥5 tests pass (2 existing + ≥3 new)
ruff check .                 # clean
python -c "from sandbox_app.domain import Role, Tenant, ErrorCode"  # 导入成功
python -c "from sandbox_app.api.health import app; print(app.routes)"  # 路由注册成功
```
