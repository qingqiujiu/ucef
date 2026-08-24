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

当前稳定版本为 **v0.9.6**：

- [源码与 OpenCode Skill](UCEF_opencode_skill_v0.9.6/)
- [安装说明](UCEF_opencode_skill_v0.9.6/README_INSTALL.md)
- [发布压缩包](UCEF_opencode_skill_v0.9.6_release.zip)
- [测试状态](UCEF_opencode_skill_v0.9.6/TEST_STATUS.md)

v0.9.6 将分析拆为业务主链、跨方法实现切片和证据三层。Skeleton、Slice、Integration Worker 通过可校验的任务胶囊协作，Coverage Gate 控制是否继续展开；HTML 默认从业务阶段进入实现细节，完整方法树保留为可展开证据。重复语义检查点不会再次写入，默认输入包压缩到约 24K，为 120K 上下文留出更大余量。

## OpenCode 集成

发布包包含：

- `ucef` Skill；
- 全权限 `ucef-java-chain` 主 Agent；
- 只读 `ucef-skeleton`、`ucef-slice`、`ucef-integration` 子 Agent；
- `padb` Skill 启动约束；
- `index-mcp_*` IDEA 语义索引工具配置；
- 独立 UCEF 工作区、SQLite 事实账本、审计和 HTML 生成运行时。

Java 项目始终是只读数据源。UCEF 的数据库、Work Unit、上下文包、运行结果和站点只写入用户指定的独立分析工作区。

## 版本历史

详见 [CHANGELOG.md](CHANGELOG.md)。历史源码快照和发布压缩包保留在仓库根目录；压缩包 SHA-256 见 [RELEASES.md](RELEASES.md)。

## 验证

v0.9.6 已通过 18 项运行时、工作区、分层调度、持久化记忆、方法树、字段谱系、OpenCode Agent 和 HTML 回归测试；发布包另做解压回归。运行时仅依赖 Python 3.10+ 标准库。
