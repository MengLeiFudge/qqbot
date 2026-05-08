# AGENTS.md - qqbot 工作流程

本文件记录本仓库的开发、验证和运行约定。README 只介绍仓库；具体工作流程以本文件为准。

## 基本原则

- 默认使用简体中文沟通。
- 优先读现有代码和测试，再决定修改方式。
- 保持实现简单直接，避免为了未来功能提前抽象。
- 修改范围要贴近用户请求，避免顺手重构无关模块。
- 不提交、不回滚用户已有改动，除非用户明确要求。

## Git Practices

- Atomic commits: one logical change per commit.
- Do not push unless explicitly approved by the user.

### 提交信息风格

提交信息使用中文 conventional style，格式固定为：

```text
类型：一句话摘要
```

类型参考 `MLJ_DSPmods`，只使用以下四类：

- `功能：` 新增用户可见能力、接口、命令或完整工作流。
- `修复：` 修正 bug、错误行为、崩溃、超时或兼容问题。
- `重构：` 调整内部结构、拆分模块、改善实现，不改变用户可见行为。
- `杂项：` 文档、测试、配置、仓库初始化、依赖和维护性变更。

示例：

```text
功能：支持 Codex 会话产物上传
修复：移除智能问答空壳入口
重构：整理 README 与 AGENTS 文档边界
杂项：初始化 qqbot 仓库
```

禁止使用空泛摘要，例如 `update`、`fix`、`修改`、`调整代码`。

### Commit Policy for Agents

**核心原则：严禁积压未提交改动。** 任何代码或文档改动必须被记录在 Git 历史中，不允许以“改了一堆文件但零 commit”的状态结束任务。即使用户没有明确要求，也应在验证通过后自动按逻辑单元 commit。

**提交流程：** 主代理根据任务复杂度和风险决定提交方式：

- 改动独立且风险较低：可直接 commit，复核后如有问题再提交修复性 commit。
- 改动跨多个模块或风险较高：完成自查和验证后按逻辑单元拆分 commit。
- 已存在用户未提交改动时：先识别改动归属，不要覆盖、回滚或混入无关 commit。

**职责要求：** 启动 Codex 或子代理修改本仓库时，prompt 中必须明确本轮 commit 策略，不能让“代码已改完但暂不提交”成为默认结束状态。

**并行场景：** 多个代理并行执行时，子代理不得各自提交；应由主代理收齐结果、完成审查后统一 commit，以避免历史冲突和责任边界不清。

**Git 串行规则：** Git 使用单一仓库锁；所有 Git 操作必须串行执行，禁止并发 `git add`、`git commit`、`git rebase`、`git stash`、`git checkout`、`git merge` 等命令。只有确认前一个 Git 命令完成且仓库锁已释放后，才能启动下一个 Git 命令。

**commit 要求：**

- 代码改动必须先运行对应测试；涉及共享路径时运行全量 `.venv/Scripts/python.exe -m pytest -q`。
- 文档-only 改动可不跑全量 pytest，但最终回复必须说明未运行代码测试的原因。
- 每个逻辑单元一个 commit，不批量堆积。
- 严禁 push，除非用户明确批准。

## 架构边界

- `src/qqbot/plugins/` 负责 NoneBot matcher、命令解析、事件入口。
- `src/qqbot/services/` 负责可测试业务逻辑、持久化和外部服务封装。
- `plugin_registry.py` 是插件元数据唯一入口；菜单、管理端和全局插件开关优先从这里读取。
- 插件不使用功能序号；菜单入口使用 `菜单+模块名称/别名` 模糊匹配。
- 新入群默认启用所有未被全局禁用的插件，不再维护每群功能开关。
- `群管助手` 只覆盖 QQ/群行为能力，不包含菜单、全局插件开关或 Bot 管理员维护入口；其相关指令和功能只允许 Bot 管理员或机器人自身触发。
- 新增插件时，先补服务层，再补 matcher；不要把复杂业务逻辑堆在 matcher 里。
- 群聊显式命令默认需要 direct-at，避免普通聊天误触发。

## 配置边界

- `.env` 只放敏感信息和本机账号，例如 OneBot token、NapCat QQ、AI API key。
- `config/qqbot.toml` 放低频变化的非敏感配置，例如路径、AI provider、默认模型。
- `run/settings/` 和 `run/ai/` 放运行时状态，例如全局插件开关、管理员、AI 对话上下文、动作审计。
- 不要把真实 `.env`、真实 `config/qqbot.toml`、`run/`、`logs/` 放进公开仓库。

## 测试分层

- `tests/` 只放长期回归测试，默认由 `.venv/Scripts/python.exe -m pytest -q` 执行。
- `.codex/tests/` 放 Codex 临时验证脚本、一次性复现用例和探索性探针，默认不进入全量 pytest。
- 临时测试如果变成必须长期防回归的行为，应整理成稳定 pytest 用例并移动到 `tests/`。
- 修改服务层、插件注册、消息规范化、AI 边界、管理 API、后台任务时，应补或更新 `tests/` 下的长期测试。
- 声称完成前必须运行真实验证命令；如果只改文档，可以说明未运行代码测试。

## 常用验证命令

```bash
.venv/Scripts/python.exe -m pytest -q
```

定向验证示例：

```bash
.venv/Scripts/python.exe -m pytest tests/test_plugin_registry.py tests/test_feature_catalog.py -q
```

确认默认 pytest 不收集 `.codex/tests/`：

```bash
.venv/Scripts/python.exe -m pytest --collect-only -q
```

## AI 与 Codex 边界

- 普通 AI 回复只负责文本生成和已白名单的本地能力编排。
- AI 不直接获得 shell、文件系统、群管、重启、上传文件等自由权限。
- 上传已有项目 zip 产物属于固定白名单能力，只能由 Bot 管理员在群聊触发；机器人只查找项目仓库内真实存在的 `.zip` 并上传，不构建、不改代码、不 push。MLJ_DSPmods 的 FE 发布流程只上传 `FractionateEverything_*.zip`，上传前删除同一群内由 Bot 上传的旧 `FractionateEverything_*.zip`。
- 涉及代码修改时，qqbot 只做中转、权限、项目路由、会话记录、结果回传和产物上传。
- qqbot 给 Codex 的 prompt 不替目标仓库规定 git、分支、提交、测试、构建、输出格式或 Markdown 规则。
- 目标仓库的 `AGENTS.md` / README / 项目规范决定 Codex 的具体执行规则。
- `@机器人 codex <项目>` 进入 Codex 会话模式，`codex` 后面必须写明确项目名或别名；未匹配项目时必须拒绝进入，避免误改仓库。
- 群聊 Codex 会话按群唯一：同一个群同时只能有一个 active Codex 会话，群内所有 Bot 管理员共享同一会话，直到发送 `退出codex`。
- 私聊 Codex 会话按管理员唯一：每个 Bot 管理员私聊只能有一个 active Codex 会话，不和群聊会话共享。
- 非 Bot 管理员不能进入、继续、执行或退出 Codex 会话；群聊中存在 active Codex 会话时，非管理员 @ Bot 也不能接管该会话。
- 执行阶段按项目加锁：同一个项目同时只能有一个 running Codex 会话，不同群可以同时讨论不同项目。
- Codex 会话讨论阶段使用只读 sandbox，执行阶段才允许写工作区。
- Codex 输出的 `.zip` 产物路径可由 qqbot 解析并上传回来源群，但只能上传目标仓库内真实存在的 zip 文件。
- 通过群聊触发的 Codex 任务，qqbot 负责把执行结果发回来源群；通过私聊触发的 Codex 任务，qqbot 只向触发用户私聊回报。
- 直接在本地 Codex 终端执行的任务默认不应主动向 QQ 群发消息；例外是 `AfterBuildEvent.exe 1` 这类本机白名单构建流程，可调用 localhost-only 管理接口推送 `afterbuild-result.json`，由 qqbot 完成 FE 产物筛选、旧包清理和上传。若请求体或 `afterbuild-result.json` 带有发布说明，qqbot 应优先发送该说明，说明内容应聚焦本次原因、修复/改动内容和实现方式，不发送文件级 diff 统计。说明消息应尽量引用刚上传的 FE zip，并根据提交前缀套用 `修复/功能/重构/杂项` 的结构化段落。
- Codex 修改 qqbot 自身项目并成功完成后，必须安排 Bot 重启，使新代码实际生效。
- 通过 qqbot 触发的自我更新，旧进程应先向来源群或私聊提示“已安排重启”，重启后在 OneBot 重新连接时再向相同目标回报连接状态。
- 直接在本地 Codex 终端修改 qqbot 时，完成提交和验证后必须调用管理端重启入口，并检查 `onebot_connected=true`、`connected_bot_count>=1`。

## 运行与重启

日常启动入口：

```powershell
Set-Location D:\project\python\qqbot
.\scripts\start_all.bat
```

管理端重启入口：

```bash
curl -s -X POST http://127.0.0.1:8080/admin/api/restart
```

重启后检查：

```bash
curl -s http://127.0.0.1:8080/admin/api/status
```

期望状态：

- `onebot_connected=true`
- `connected_bot_count>=1`

## 文档边界

- README 放仓库简介、能力概览、目录、配置、启动、管理端和主要用户入口。
- AGENTS 放开发流程、架构约束、测试分层、AI/Codex 边界、验证和重启规则。
- 具体设计讨论和阶段计划放 `.codex/drafts/`、`.codex/plans/`。
- 不要把临时讨论流水账写进 README。
