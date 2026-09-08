# OpenCode Agent 配置

## 默认角色

`ucef-java-chain` 是主分析者：使用 `index-mcp` 理解只读源码，使用 `obsidian-mcp` 维护全局笔记、图形和断点；仅在当前结论确实依赖数据库事实时加载 `padb`。

`ucef-probe` 是可选子任务：只用 `index-mcp` 回答一个独立问题，不写Obsidian，不维护全局状态。

## 权限

主Agent只需：

```yaml
"*": ask
skill: allow
"index-mcp_*": allow
"obsidian-mcp_*": allow
```

Probe只需 `skill` 与 `index-mcp_*`。主 Agent 对未知工具使用 `ask`，以便真实环境中的 `padb` 或 Obsidian CLI 在首次使用时获得明确授权；已知 MCP 直接允许。源项目仍由提示词约束为只读。

如果 MCP 服务器注册名不同，修改权限前缀即可。若 `padb` 需要特定工具，将其自身说明中的最小只读权限加入主 Agent；不要猜测工具名或开放全局权限。Skill 按能力选择工具，不依赖某个固定方法名，也不需要自定义 `ucef.ts`。

## 工作方式

1. 使用Obsidian恢复当前调查状态和焦点笔记；
2. 在长时间检索前确认 Obsidian 具备真实写入路径；
3. 使用索引 MCP 围绕当前问题定向查询；
4. 源码无法确认且数据库事实会改变结论时，按需加载 `padb`；
5. 理解形成后局部更新业务笔记与恢复胶囊并完成自检；
6. 根据内容生成真正有解释力的图；
7. 在切换焦点或中断前写清下一步准确入口；
8. 主 Agent 统一合并可选 Probe 结果。

不创建Planner/Block/Finalizer队列，不提交业务实体，不运行覆盖率评分，不生成HTML站点。
