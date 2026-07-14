# personal-health-agent

本地优先的个人健康档案、趋势管理、辐射剂量账本与就医沟通辅助系统。它不提供自动诊断、
处方、检查医嘱、急救或个人癌症概率。所有正式数据通过 `health` CLI 进入本地 SQLite；
Hermes 只能调用 CLI，不能执行 SQL。

## 当前版本

版本 `0.3.0` 已实现数据库迁移 3、症状时间轴、复查/复诊和预约管理、科室相关就诊摘要、
病理与医生意见候选、Dose Screen 局部确认、普通 DICOM 剂量字段回退、扩充化验映射和
统一 JSON 错误。Apple Health、生活方式和正式微信部署仍未实现。详见
[开发计划](docs/DEVELOPMENT_PLAN.md)。

## 安装与初始化

```bash
cd /Users/marionliew/personal-health-agent
uv sync --extra test --extra backup
uv run health init --json
uv run health doctor --json
uv run health db verify --json
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

普通报告先 `record import --dry-run`，确认保存候选后，用 `record candidates IMPORT_ID`
查看并通过 `record confirm-candidates` 局部确认。DICOM 剂量也必须先 dry-run；只有结构化
RDSR 可在确认后作为设备记录入账；Dose Screen 必须按候选 ID 局部确认，Total DLP 不与
事件 DLP 重复累计。普通 DICOM 缺失 DLP 时保持为空，不从切片数推算有效剂量。

常用日常管理命令：

```bash
uv run health symptoms add --name 咽喉疼痛 --location 咽喉 --dry-run --json
uv run health followup add --title 影像复查 --due '6至12个月' --dry-run --json
uv run health followup pending --json
uv run health visit-summary --department 耳鼻喉科 --json
uv run health doctor-questions --department 耳鼻喉科 --json
uv run health dicom dose-screen data/imports/DOSE_SCREEN.txt --dry-run --json
```

所有 `--json` 错误统一写入 stdout，使用稳定错误码并以非零状态退出；不会向微信输出堆栈、
数据库路径或原始隐私字段。
