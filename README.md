# 个人医疗证据管理（personal-health-manager）

把本地检查报告整理成可核对的记录，带着证据去问医生，而不是让 AI 替医生下结论。

```bash
uv sync --extra test
uv run health init --json
uv run health doctor --json
uv run health visit-summary --department 耳鼻喉科 --json
```

报告、病灶测量、症状与复诊提醒留在本地 SQLite；导入的解析结果先预览，再由人确认。问诊摘要帮助梳理已有资料和待问的问题，但不替代原报告或临床判断。当前仓库的 Python 包和命令仍叫 `personal-health-agent` / `health`；Hermes Skill 叫 `personal-health-manager`。

## 本地运行

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。在仓库根目录执行：

```bash
uv sync --extra test --extra backup
uv run health init --json
uv run health db verify --json
```

默认数据库在 `data/database/health.sqlite3`。不要把真实报告、数据库、导出包或身份资料加入 Git。`config/default.yaml` 是随仓库发布的默认值；如需配置 Hermes 的本地附件缓存，参考 `config/example.yaml` 创建自己的 `config/hermes.yaml`，仅允许你信任的精确目录。仓库当前仍追踪一个历史 `config/hermes.yaml`；**`.gitignore` 无法取消追踪，公开发布前必须解决历史隐私审查中的阻断项**。

## 从报告到问诊

把资料放入 `data/imports/`；任何医疗事实都应核对原件，写入前先检查预览：

```bash
uv run health record import data/imports/report.pdf --dry-run --json
# 核对预览后，明确同意才改用 --confirm；不要直接批量确认 OCR 候选。
uv run health visit-summary --department 耳鼻喉科 --json
uv run health doctor-questions --department 耳鼻喉科 --json
```

扫描 PDF 的 OCR 默认关闭；启用本地 OCR 仍须逐项核对日期、数值、单位、左右侧和阴阳性。GPT 分析导出只生成本地文件，不自动上传；先预览，再确认，并在分享前自行复核脱敏结果：

```bash
uv run health export gpt-bundle --output review.json --dry-run --json
```

目前已有症状时间线、随访、结构化报告候选、影像和辐射剂量账本；正式病灶管理（`health lesions
create/update/link-source/add-measurement/history`，不可变 UUID 与可读编号、证据类型保留、双侧
群体描述不归属单颗）与证据链导出（`health export lesion-bundle/visit-bundle/record-index/case-bundle`，
原文引用与系统摘要分离、原件打包校验）已实现；可点击原始 PDF 的医生速览 PDF 尚未实现，不要把
现有导出当成排版 PDF。[开发计划](docs/DEVELOPMENT_PLAN.md)记录范围，[医疗边界](docs/MEDICAL_SAFETY.md)说明限制。紧急情况请联系当地急救服务。

## 开发与安全

```bash
uv run pytest
uv run ruff check .
```

[贡献指南](CONTRIBUTING.md)说明如何使用虚构数据提交改动；发现漏洞或隐私泄露请按[安全政策](SECURITY.md)私下报告。代码按 [MIT](LICENSE) 授权；患者资料和第三方报告不因此获得公开授权。
