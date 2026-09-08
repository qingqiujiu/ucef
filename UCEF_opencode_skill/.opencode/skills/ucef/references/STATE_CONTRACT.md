# UCEF 调查状态协议

`.ucef/state.json` 是紧凑控制面。它保存当前调查到哪里，不保存长篇推理，也不规定业务对象。

## 顶层结构

```json
{
  "version": 1,
  "analysis_id": "ANALYSIS-...",
  "goal": "用户真正需要回答的问题",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "current_focus": ["Q-001"],
  "questions": [],
  "claims": [],
  "evidence": [],
  "artifacts": [],
  "sources": [],
  "checkpoint": {
    "summary": "",
    "current_focus": [],
    "next_actions": [],
    "updated_at": null
  }
}
```

`questions`、`claims`、`evidence`、`artifacts` 和 `sources` 中的对象都必须有稳定 `id`。其他字段按当前任务自由增加；Runtime 不限制业务字段。

## 问题状态

- `unexplored`：尚未探索。
- `exploring`：正在探索。
- `partially_resolved`：已有重要认识，但仍有可能影响结论的断点。
- `resolved`：达到用户需要的解释深度，关键依据可定位。
- `blocked`：缺少继续确认所需的材料或权限。
- `deferred`：当前价值较低，明确暂缓。

状态可以回退。发现新证据后，`resolved` 可以重新变成 `exploring` 或 `partially_resolved`。

## 结论状态

- `hypothesis`
- `supported`
- `uncertain`
- `contradicted`
- `superseded`

推荐结论字段：

```json
{
  "id": "C-001",
  "statement": "一句话结论",
  "status": "supported",
  "confidence": "high",
  "question_refs": ["Q-001"],
  "evidence_refs": ["E-001"],
  "note_ref": "[[业务全链路#^c-001]]",
  "caveat": null
}
```

## 笔记制品

`artifacts` 只管理笔记是否需要继续补充，不限制笔记类型：

```json
{
  "id": "A-001",
  "kind": "自由字符串",
  "subject": "笔记说明",
  "status": "current",
  "note_ref": "[[业务全链路]]",
  "related_refs": ["Q-001", "C-001"]
}
```

建议状态为 `planned`、`draft`、`current`、`needs_update`、`blocked`。`kind` 由模型按任务决定，不建立固定业务枚举。

## 更新操作

`ucef_state_update` 接受一组原子操作：

```json
[
  {
    "op": "upsert",
    "collection": "questions",
    "item": {
      "id": "Q-001",
      "question": "当前真正需要查清的问题",
      "importance": "critical",
      "status": "exploring",
      "current_understanding": "目前已经确认什么",
      "note_ref": "[[调查工作台#^q-001]]",
      "next_action": "下一步最有价值的动作"
    }
  },
  {
    "op": "set",
    "field": "current_focus",
    "value": ["Q-001"]
  }
]
```

支持：

- `upsert`：按 `id` 新增或增量合并对象；
- `remove`：按 `collection + id` 删除对象；
- `set`：设置 `goal` 或 `current_focus`。

不要用删除掩盖被推翻的历史结论。通常应保留原结论并改为 `contradicted` 或 `superseded`。

## 更新时机

状态按理解事件更新，不按工具调用次数更新。阅读文件但没有改变理解时不更新；形成新问题、改变结论、切换重点、合并子任务或准备中断时更新。

主 Agent 是唯一状态写入者。子 Agent 返回紧凑调查结果，由主 Agent 判断后合并，避免并发覆盖和全局语义冲突。
