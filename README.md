# AI Pipeline Sandbox

完整小项目：给「AI 无人化开发流水线」做真实 Issue → PR 演练。

## 结构

- `src/sandbox_app/` 业务代码
- `tests/` 自动化测试
- GitHub Actions：lint + test

## 本地

```bash
pip install -e ".[dev]"
pytest
ruff check .
```
