# UCEF

UCEF（Unified Code Excavation Framework）是面向大型 Java 系统的业务链路精读框架。它把多个 Java 项目和生产配置视为只读数据源，在独立分析工作区中持续积累可回查事实，最终生成面向“懂 Java、但不了解该系统”读者的业务执行档案。

它关注的不是简单调用关系，而是：

- 多项目共用入口和跨项目调用；
- 配置、Bean、租户、渠道等条件驱动的路由；
- 方法内部步骤及字段读取、转换、覆盖、拆合和传递；
- 字段从入口到外部请求、响应消费、落库和返回的完整谱系；
- 外部接口入参来源、反参用途、失败语义和业务效果；
- 长链路分析中的持久化事实、断点恢复和已分析知识复用。

## 持续开发版

从 1.1 开始，开发版固定维护在不带版本号的目录中，不再为每次修改新建源码文件夹：

- [持续更新的 OpenCode Skill](UCEF_opencode_skill/)
- [安装与更新说明](UCEF_opencode_skill/README_INSTALL.md)
- [Agent 配置](UCEF_opencode_skill/OPENCODE_AGENT_SETUP.md)

当前开发版采用“提示词主导分析、Obsidian 承载知识、轻量工具保存状态”的新架构。主模型负责理解业务全链路、重要字段生命周期和逐方法下钻；程序只维护紧凑 JSON 状态、断点、UTF-8 原子写入和链接校验，不再建立固定事实图或生成 HTML。

最新发布快照为 **v1.0.0**，保留在 [UCEF_opencode_skill_v1.0.0/](UCEF_opencode_skill_v1.0.0/) 及对应 ZIP 中。历史源码快照和发布包不会随开发版更新。

## OpenCode 集成

历史发布包通常包含：

- `ucef` Skill；
- 全权限 `ucef-java-chain` 主 Agent；
- 有硬 steps 上限的 `ucef-planner`、`ucef-block`、`ucef-finalizer` 子 Agent；
- `padb` Skill 启动约束；
- `index-mcp_*` IDEA 语义索引工具配置；
- 独立 UCEF 工作区、SQLite 事实账本、审计和 HTML 生成运行时。

源码项目始终是只读数据源。持续开发版只向用户指定的 Obsidian 分析目录写入 Markdown 与 `.ucef/state.json`；旧发布版仍按各自说明使用独立工作区。

## 版本历史

详见 [CHANGELOG.md](CHANGELOG.md)。历史源码快照和发布压缩包保留在仓库根目录；压缩包 SHA-256 见 [RELEASES.md](RELEASES.md)。

## 验证

持续开发版在提交前进行 Skill 结构、Python 语法、JSON/UTF-8、最小状态更新和 Obsidian 链接静态校验。本次架构重写不运行智能体测试，也未制作发布包。
