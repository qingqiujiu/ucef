# UCEF

UCEF（Unified Code Excavation Framework）是面向大型 Java 系统的业务链路精读框架。它把多个 Java 项目和生产配置视为只读数据源，在独立分析工作区中持续积累可回查事实，最终生成面向“懂 Java、但不了解该系统”读者的业务执行档案。

它关注的不是简单调用关系，而是：

- 多项目共用入口和跨项目调用；
- 配置、Bean、租户、渠道等条件驱动的路由；
- 方法内部步骤及字段读取、转换、覆盖、拆合和传递；
- 字段从入口到外部请求、响应消费、落库和返回的完整谱系；
- 外部接口入参来源、反参用途、失败语义和业务效果；
- 长链路分析中的持久化事实、断点恢复和已分析知识复用。

## 当前版本

当前稳定版本为 **v0.10.0**：

- [源码与 OpenCode Skill](UCEF_opencode_skill_v0.10.0/)
- [安装说明](UCEF_opencode_skill_v0.10.0/README_INSTALL.md)
- [发布压缩包](UCEF_opencode_skill_v0.10.0_release.zip)
- [测试状态](UCEF_opencode_skill_v0.10.0/TEST_STATUS.md)

v0.10.0 将默认流程压缩为 ScenarioPlan、BusinessBlock、ScenarioOverview 三类最终产物。STANDARD 最多 6 次模型任务和 30 分钟；子 Agent 直接校验入库，父 Agent 只接收 receipt，不再多层搬运与重写。Runtime 只提供紧凑历史业务块索引和同键复用候选，避免重读旧报告。HTML 从计划开始增量出现，业务块默认展开，字段、外部接口、落库和失败结果横向汇总，方法树仅作为折叠技术证据。

## OpenCode 集成

发布包包含：

- `ucef` Skill；
- 全权限 `ucef-java-chain` 主 Agent；
- 有硬 steps 上限的 `ucef-planner`、`ucef-block`、`ucef-finalizer` 子 Agent；
- `padb` Skill 启动约束；
- `index-mcp_*` IDEA 语义索引工具配置；
- 独立 UCEF 工作区、SQLite 事实账本、审计和 HTML 生成运行时。

Java 项目始终是只读数据源。UCEF 的数据库、Work Unit、上下文包、运行结果和站点只写入用户指定的独立分析工作区。

## 版本历史

详见 [CHANGELOG.md](CHANGELOG.md)。历史源码快照和发布压缩包保留在仓库根目录；压缩包 SHA-256 见 [RELEASES.md](RELEASES.md)。

## 验证

v0.10.0 已通过 21 项运行时、硬预算、直接提交、幂等回执、工作区、旧数据兼容、方法树、字段谱系、OpenCode Agent 和 HTML 回归测试；发布包另做解压回归。运行时仅依赖 Python 3.10+ 标准库。
