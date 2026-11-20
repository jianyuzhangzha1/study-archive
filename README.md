# 学迹 Study Archive — 一期开发基线 v0.1.0

日期：2026-11-08。面向家庭私有部署的高中数学、英语、语文作业档案。

## 当前交付的性质

这是**可运行的纵向开发基线＋一期设计契约**，不是已经完成生产验收的产品，也没有部署到用户的 PVE。前端连接真实数据库；默认 AI_MODE=mock，输出始终标为“演示 / 无法判断”，不产生真实成绩。配置真实兼容 API 后可尝试文本初审、同类题生成和图像转录；这些外部调用本次未实测。

已实现：作业创建和查询、图片上传与原图查看、手动题目录入、作答版本保存、持久化任务队列、AI适配接口、人工反馈、错题确认、订正、原题复测、同类题候选审核、复测通过状态、基础报表、JSON导出。

暂未实现：自动拆题及区域框选、语音输入、HEIC/PDF导入、知识目录管理界面、家长/学生分别登录、自动复习调度、在线数据库升级、删除/恢复管理、公共SaaS隔离、LoRA。题目与答案暂不原位修改；录入有误可新建题目，正式试用前补充题目版本修订。

## 快速开始：本地开发

Python 3.12。所有命令在项目根目录执行。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
export APP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export AI_MODE=mock
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

保留 APP_TOKEN，在第二个终端进入项目并激活同一虚拟环境，运行：

```bash
python -m app.worker
```

默认 SQLite 仅用于本地验证。浏览器打开 http://127.0.0.1:8080，输入 APP_TOKEN。令牌不会写入浏览器持久存储。应用重启前需再次设置同一令牌，或按自己的进程管理方式保管环境变量。不要在聊天中发送真实密钥。

## 家庭部署：PostgreSQL＋Compose

```bash
cp .env.example .env
```

编辑 .env，为 APP_TOKEN 和 DB_PASSWORD 分别填入随机值；DB_PASSWORD 使用随机十六进制或URL安全字符，避免数据库连接URL转义问题。然后：

```bash
docker compose up -d --build
docker compose ps
```

默认只绑定 VM 的 127.0.0.1。若由另一台 CT310 访问，必须将 APP_BIND_IP 改为此 VM 的固定内网 IP，并在 VM/PVE 防火墙只允许 CT310 访问8080；CT310配置HTTPS反向代理。公网使用前必须完成正式身份、配额和端到端验收，当前共享令牌不等于SaaS权限系统。

## AI配置

```dotenv
AI_MODE=openai-compatible
AI_BASE_URL=https://YOUR_PROVIDER_API_PREFIX
AI_API_KEY=YOUR_SECRET
AI_MODEL=YOUR_AVAILABLE_MODEL
AI_VISION_ENABLED=false
```

适配器在 BASE_URL 后追加 /chat/completions，使用 Bearer、JSON Object响应格式和 max_tokens。供应商支持范围有差异，需要做小样本联调；原生Gemini协议未实现，不能将其普通端点直接填入并假定兼容。图像须显式启用，供应商模型也须支持image_url输入。外发内容：题干、参考答案、学生作答及说明；图像转录时发送整张选定照片，当前没有自动匿名化，使用前请裁去姓名学号。模型结果经字段和原文引用校验后保存。

没有可靠答案时AI意见仍只是初审；演示模式的同类题生成会明确失败，不生成假题冒充真实结果。失败任务需用新Idempotency-Key人工重试，系统不自动重复可能计费的调用。

## 第一次验收

1. 创建一份作业，上传一张不含个人信息的JPEG/PNG。
2. 手工输入一道题及可靠参考答案，保存错误的初次作答。
3. 调用AI初审；mock模式应显示“无法判断”，错题本保持为空。
4. 人工确认错误并填写错因；错题本出现记录。
5. 保存订正作答，标明是否使用提示，确认正确。
6. 安排原题回顾，独立作答后确认正确；状态变为“原题复测通过”。
7. 配置真实API后生成同类题，人工检查后批准，安排同类题验证。仅独立且确认正确可通过。
8. 查询报表与导出，核对初稿分母及辅助作答记录。

## 开发验证

```bash
python -m pytest -q
PYTHONPATH=. python scripts/export_contracts.py
```

生成 docs/openapi.json 和 db/001_initial.sql。开发启动用create_all，仅支持空库初始化，不是升级迁移器；后续结构变更必须使用版本迁移。

## 文件导航

- docs/PHASE1_DESIGN.md：完整一期设计、范围、流程、Web、数据库、基础设施、接口和验收。
- docs/openapi.json：由实现自动生成的接口契约。
- db/001_initial.sql：由ORM模型生成的PostgreSQL初始DDL。
- app/：FastAPI、数据模型、AI适配器、独立Worker。
- web/：响应式基础界面，无第三方CDN。
- tests/：流程、权限、幂等、文件及失败路径测试。
- docs/VALIDATION.md：实际验证结果与未验证项。
