# personal-health-agent

本地优先的个人健康档案、趋势管理、辐射剂量账本与就医沟通辅助系统。它不提供自动诊断、
处方、检查医嘱、急救或个人癌症概率。所有正式数据通过 `health` CLI 进入本地 SQLite；
Hermes 只能调用 CLI，不能执行 SQL。

## 当前版本

版本 `0.5.6` 增加结构化医院来源字段；扫描PDF支持显式本地Vision OCR预览，双侧/多个淋巴结保留二维代表测量，
OCR默认关闭且所有字段必须人工确认；同时继承0.5.4对病理免疫组化“部分+”、Ki-67约数、补充报告日期、全部建议及
送检碎组织尺寸边界；同时继承0.5.3的PDF布局保留解析、凝血与扩展血常规、喉镜/鼻内镜
和MR报告支持，修复
表格序号错作检验结果、`PCT`误作CT及`RSI`误作血清铁，并让dry-run按SHA检查重复；同时
保留颈部报告修复和经过 dry-run/confirm 门控的安全重解析，以及Hermes v0.16/微信集成、
精确缓存目录白名单、
CLI-only Skill 包装和只读影像列表，以及
数据库迁移 4 和 Personal Health Profile 长期管理层，以及 0.3.0 的
症状时间轴、复查/复诊和预约管理、科室相关就诊摘要、
病理与医生意见候选、Dose Screen 局部确认、普通 DICOM 剂量字段回退、扩充化验映射和
统一 JSON 错误。Apple Health 和生活方式模块仍未实现。详见
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

已保存但尚未确认候选的报告可运行 `health record reparse SOURCE_ID --dry-run --json` 预览
新解析结果，人工确认后再将同一命令改为 `--confirm`。重解析只会替换尚未确认的旧候选，
不会改变已确认或已拒绝的医疗事实。

扫描PDF默认不执行OCR。用户明确同意后，可用
`health record reparse SOURCE_ID --ocr --dry-run --json` 进行完全本地的OCR预览。OCR候选
置信度被限制为低置信度，日期、数字、小数点、单位、左右侧、位置及阴阳性必须逐项核对。

常用日常管理命令：

```bash
uv run health symptoms add --name 咽喉疼痛 --location 咽喉 --dry-run --json
uv run health followup add --title 影像复查 --due '6至12个月' --dry-run --json
uv run health followup pending --json
uv run health visit-summary --department 耳鼻喉科 --json
uv run health doctor-questions --department 耳鼻喉科 --json
uv run health dicom dose-screen data/imports/DOSE_SCREEN.txt --dry-run --json
uv run health profile summary --json
uv run health profile priorities --json
uv run health imaging list --json
```

所有 `--json` 错误统一写入 stdout，使用稳定错误码并以非零状态退出；不会向微信输出堆栈、
数据库路径或原始隐私字段。

长期问题通过 `profile condition-add/scar-add/hpv-add/treatment-add/image-add/immune-add/risk-add`
先预览后确认。照片仅用于大小、数量和外观的纵向记录，不进行自动诊断。Profile 只输出
已知问题、变化、治疗、当前状态、风险因素、观察点和管理建议，不输出疾病概率或综合评分。

Hermes 集成：

```bash
./hermes_skill/install.sh
./hermes_skill/verify.sh
hermes gateway restart
hermes skills list
```

具体微信路由、权限和写操作确认流程见
[Hermes 集成文档](docs/HERMES_INTEGRATION.md)。
