# personal-health-agent

本地优先的个人健康档案、趋势管理、辐射剂量账本与就医沟通辅助系统。它不提供自动诊断、
处方、检查医嘱、急救或个人癌症概率。所有正式数据通过 `health` CLI 进入本地 SQLite；
Hermes 只能调用 CLI，不能执行 SQL。

## 当前版本

版本 `0.1.0` 建立了安全边界、配置、稳定 JSON 响应、版本化数据库骨架、审计模型和基础
运维命令。详见 [开发计划](docs/DEVELOPMENT_PLAN.md) 中按实际状态标记的范围。

## 安装与初始化

```bash
cd /Users/marionliew/personal-health-agent
uv sync --extra test --extra backup
uv run health init --json
uv run health doctor --json
```

数据库默认位于 `data/database/health.sqlite3`，原始资料和运行数据均被 Git 忽略。导入文件
应先放入 `data/imports`、`data/dicom` 或 `data/apple_health`，CLI 拒绝项目外路径。

## 开发验证

```bash
uv run pytest
uv run ruff check .
```

医疗信息请始终由现实医生结合病史和检查判断。行动等级 A 仅表示应立即现实就医，系统本身
不是急救服务。

