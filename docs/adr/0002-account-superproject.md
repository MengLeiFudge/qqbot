# ADR-0002：账号级 Superproject 与框架 Fork

状态：Accepted

日期：2026-08-30

## 背景

原工作区把 AstrBot Core 参考源码、根插件、根配置、统一运行数据和双账号启动器混在同一仓库；MaiBot 又以无 Git 历史的源码副本存在。结果是框架不能从自身目录独立启动或更新，根脚本同时承担账号、框架和运行态细节，AstrBot 的云栖/夜凛双平台合同也让固定功能 owner、命令去重和故障边界不清晰。

用户需要四个账号保持稳定身份与端口，但框架分配可以演进：云栖负责聊天和全部固定功能，夜凛只聊天，星遥与月澄当前只保留协议端。

## 决策

1. `MengLeiFudge/qqbot` 作为账号级 superproject，只维护两个框架 gitlink、NapCat、账号映射、根编排和跨项目文档。
2. AstrBot 与 MaiBot 分别使用 `MengLeiFudge/AstrBot`、`MengLeiFudge/MaiBot` fork 的 `deployment` 分支；各自保存 Core、本地插件、脱敏示例和项目脚本，实际配置、数据、日志与环境物理位于项目内但不进入 Git。
3. 根用户启动合同固定为 `all/yunqi/yelin`。`napcat/accounts.json` 保存账号、QQ、固定端口、连接方向和当前框架入口；根命令不暴露框架名。
4. 云栖 `1443944862:6200` 只使用 AstrBot，并成为全部固定功能的唯一运行 owner；AstrBot 不保留双 profile、双 worker 或跨账号 command claim。
5. 夜凛 `2629227874:6201` 只使用 MaiBot。`napcat_adapter` 是唯一允许启用的第三方插件，所有 `qqbot_*` 源码保留但由启动前 chat-only 策略强制禁用。
6. 星遥 `3056830689:6202` 与月澄 `3109326090:6203` 当前没有 Bot Core，也不加入默认根启动组。
7. 框架只在显式更新时合入官方最新稳定 Release；启动不自动升级，不追踪主分支每个提交。更新和提交先发生在 fork，再更新 qqbot gitlink。

## 结果

- 每个框架可以从自身目录配置、启动和更新，不读取根 `config/plugins/data`。
- 根编排只处理账号顺序与整体 ready；以后更换账号框架时不改变用户 Target 或固定端口。
- 两个框架的插件实现分别演进。长期新增固定功能需要同时维护两侧源码，但 MaiBot 侧保持运行禁用；本次迁移不补齐历史功能差异。
- 三个仓库必须分别提交、审查和推送。根仓只能记录 submodule commit，不能保存子项目内尚未提交的普通文件。
- 首次克隆需要初始化 submodule，并单独恢复三个项目的本机运行态。真实密钥、QQ 登录态、数据库、日志和会话数据不具备 Git 可移植性。

## 被否决方案

- 官方 Core submodule 加根运行 wrapper：MaiBot 大量路径按源码位置解析，需长期维护广泛路径补丁；两框架结构也会不一致。
- 将两个框架 vendor/subtree 到 qqbot：可以单仓保存，但失去独立项目历史、独立 upstream 合并和清晰发布边界。
- 继续由单 AstrBot 承载云栖与夜凛：不符合云栖全功能、夜凛 MaiBot 纯聊天的账号职责，也保留不必要的跨账号调度复杂度。
