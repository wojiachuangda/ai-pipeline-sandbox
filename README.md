# 多智能体管理平台（模块化演进）

源需求：自动化开发底座仓库 `goal.md`  
拆分存根：`docs/goal-split/stubs/T-00x.md`  
策略：**一个模块一条 PR，合并进 main 后再做下一模块**。

## 当前已合入

- **T-001** 仓库骨架与领域模型基线（本提交）

## 本地

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
uvicorn agent_platform.api.app:app --reload --port 8090
# GET http://127.0.0.1:8090/health/live
# GET http://127.0.0.1:8090/health/ready
```

## 模块边界（T-001）

| 包路径 | 职责 |
|---|---|
| `agent_platform.domain` | 角色、租户上下文、统一错误码 |
| `agent_platform.api` | HTTP 健康检查与后续 API |
| `tests/` | 自动化测试 |

Agent 业务 API 从 **T-002** 开始。
