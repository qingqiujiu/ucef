# OpenCode Agent 配置

## 默认角色

`ucef-java-chain` 是主分析者：使用 `index-mcp` 理解只读源码，使用 `obsidian-mcp` 维护全局笔记、图形和断点。

`ucef-probe` 是可选子任务：只用 `index-mcp` 回答一个独立问题，不写Obsidian，不维护全局状态。

## 权限

主Agent只需：

```yaml
skill: allow
"index-mcp_*": allow
"obsidian-mcp_*": allow
```

Probe只需 `skill` 与 `index-mcp_*`。默认拒绝其他操作，以确保源项目不会被修改。

如果MCP服务器注册名不同，修改权限前缀即可。Skill按能力选择工具，不依赖某个固定方法名，也不需要自定义 `ucef.ts`。

## 工作方式

1. 使用Obsidian恢复当前调查状态和焦点笔记；
2. 使用索引MCP围绕当前问题定向查询；
3. 理解形成后局部更新业务笔记与恢复胶囊；
4. 根据内容生成真正有解释力的图；
5. 在切换焦点或中断前写清下一步准确入口；
6. 主Agent统一合并可选Probe结果。

不创建Planner/Block/Finalizer队列，不提交业务实体，不运行覆盖率评分，不生成HTML站点。
