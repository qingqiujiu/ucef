import { tool } from "@opencode-ai/plugin"
import path from "path"

type ToolContext = { worktree: string }

async function invoke(
  context: ToolContext,
  workspace: string,
  command: string[],
  payload?: unknown,
): Promise<string> {
  const script = process.env.UCEF_STATE_SCRIPT || path.join(
    context.worktree,
    ".opencode",
    "skills",
    "ucef",
    "scripts",
    "ucef_state.py",
  )
  const python = process.env.UCEF_PYTHON || "python"
  const proc = Bun.spawn([python, script, "--workspace", workspace, ...command], {
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
      PYTHONUNBUFFERED: "1",
    },
  })
  if (payload !== undefined) {
    proc.stdin.write(new TextEncoder().encode(JSON.stringify(payload)))
  }
  proc.stdin.end()
  const [stdoutBytes, stderrBytes, exitCode] = await Promise.all([
    new Response(proc.stdout).arrayBuffer(),
    new Response(proc.stderr).arrayBuffer(),
    proc.exited,
  ])
  const stdout = new TextDecoder("utf-8", { fatal: true }).decode(stdoutBytes)
  const stderr = new TextDecoder("utf-8", { fatal: true }).decode(stderrBytes)
  if (exitCode !== 0) {
    throw new Error((stderr || stdout || `UCEF exited with ${exitCode}`).trim())
  }
  return stdout.trim()
}

export const workspace_init = tool({
  description: "Create or resume the minimal UCEF Obsidian analysis directory. Keeps existing notes and state unchanged.",
  args: {
    workspace: tool.schema.string().describe("Absolute Obsidian analysis directory"),
    goal: tool.schema.string().optional().describe("Initial user goal; free text, not a schema"),
    analysis_id: tool.schema.string().optional(),
  },
  async execute(args, context) {
    const command = ["init"]
    if (args.goal) command.push("--goal", args.goal)
    if (args.analysis_id) command.push("--analysis-id", args.analysis_id)
    return invoke(context as ToolContext, args.workspace, command)
  },
})

export const state_read = tool({
  description: "Read compact UCEF focus, unresolved critical questions, recent changes, and checkpoint. Full state is opt-in.",
  args: {
    workspace: tool.schema.string(),
    view: tool.schema.enum(["summary", "full"]).default("summary"),
    ids: tool.schema.string().optional().describe("Optional comma-separated question, claim, evidence, artifact, or source IDs"),
  },
  async execute(args, context) {
    const command = ["status", "--view", args.view]
    if (args.ids) command.push("--ids", args.ids)
    return invoke(context as ToolContext, args.workspace, command)
  },
})

export const state_update = tool({
  description: "Atomically update investigation state after understanding changes. Upsert free-form items; no business entity schema or coverage score.",
  args: {
    workspace: tool.schema.string(),
    operations: tool.schema.array(tool.schema.object({}).passthrough()).describe(
      "Operations from STATE_CONTRACT.md: upsert/remove collection items or set goal/current_focus",
    ),
  },
  async execute(args, context) {
    return invoke(context as ToolContext, args.workspace, ["update"], args.operations)
  },
})

export const state_checkpoint = tool({
  description: "Save a compact interruption checkpoint and refresh the Obsidian investigation dashboard.",
  args: {
    workspace: tool.schema.string(),
    summary: tool.schema.string().describe("What is now understood; keep concise"),
    current_focus: tool.schema.array(tool.schema.string()).optional(),
    next_actions: tool.schema.array(tool.schema.string()).optional(),
  },
  async execute(args, context) {
    return invoke(context as ToolContext, args.workspace, ["checkpoint"], {
      summary: args.summary,
      current_focus: args.current_focus,
      next_actions: args.next_actions || [],
    })
  },
})

export const workspace_validate = tool({
  description: "Check UCEF state references, UTF-8 Markdown readability, Obsidian Wikilinks, anchors, and source availability. Does not judge analysis by counts.",
  args: { workspace: tool.schema.string() },
  async execute(args, context) {
    return invoke(context as ToolContext, args.workspace, ["validate"])
  },
})
