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

当前开发版采用“强提示词主导推理、Obsidian 承载知识、现有 MCP/Skill 提供事实能力”的架构。主模型通过 `index-mcp` 理解源码，在确有需要时通过用户已有的 `padb` 查询数据库，并使用可写的 `obsidian-mcp` 或现有 Obsidian Skill/CLI 维护断点与交付。模型负责理解业务全链路、分支原因、重要字段生命周期、关键模块和逐方法下钻，并依据内容自主选择时序图、流程图、状态图、ER 图、关系图或决策图。UCEF 不再提供自建 Runtime、状态脚本、JSON 控制面、SQLite 事实图或 HTML 生成器。

最新发布快照为 **v1.0.0**，保留在 [UCEF_opencode_skill_v1.0.0/](UCEF_opencode_skill_v1.0.0/) 及对应 ZIP 中。历史源码快照和发布包不会随开发版更新。

## OpenCode 集成

历史发布包通常包含：

- `ucef` Skill；
- 全权限 `ucef-java-chain` 主 Agent；
- 有硬 steps 上限的 `ucef-planner`、`ucef-block`、`ucef-finalizer` 子 Agent；
- `padb` Skill 启动约束；
- `index-mcp_*` IDEA 语义索引工具配置；
- 独立 UCEF 工作区、SQLite 事实账本、审计和 HTML 生成运行时。

源码项目始终是只读数据源。持续开发版通过已有 `index-mcp` 检索代码，通过可写的 `obsidian-mcp` 或现有 Obsidian Skill/CLI 维护 Markdown、Wikilink、块引用和 Mermaid 图，并在必要时加载已有 `padb` 查询数据库。UCEF 只规定这些能力的启用条件和证据纪律，不重复封装工具。旧发布版仍按各自说明使用独立工作区。

## 版本历史

详见 [CHANGELOG.md](CHANGELOG.md)。历史源码快照和发布压缩包保留在仓库根目录；压缩包 SHA-256 见 [RELEASES.md](RELEASES.md)。

## 验证

持续开发版在提交前仅进行 Skill 结构、引用路径、权限声明、UTF-8 文本和 Git 差异静态校验。本次架构重写不运行智能体测试，也不制作发布包。
