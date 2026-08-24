import { tool } from "@opencode-ai/plugin"
import path from "path"

type ToolContext = { worktree: string }

async function invoke(
  context: ToolContext,
  workspace: string,
  command: string[],
  payload?: string,
): Promise<string> {
  const configured = process.env.UCEF_SCRIPT
  const script = configured || path.join(
    context.worktree,
    ".opencode",
    "skills",
    "ucef",
    "scripts",
    "ucef.py",
  )
  const python = process.env.UCEF_PYTHON || "python"
  const proc = Bun.spawn(
    [python, script, "--workspace", workspace, ...command],
    { stdin: "pipe", stdout: "pipe", stderr: "pipe" },
  )
  if (payload !== undefined) {
    proc.stdin.write(payload)
  }
  proc.stdin.end()
  const stdout = await new Response(proc.stdout).text()
  const stderr = await new Response(proc.stderr).text()
  const exitCode = await proc.exited
  if (exitCode !== 0) {
    throw new Error((stderr || stdout || `UCEF exited with ${exitCode}`).trim())
  }
  return stdout.trim()
}

export const control_start = tool({
  description: "Start one hard-budget UCEF scenario analysis. Returns the run and planner task IDs.",
  args: {
    workspace: tool.schema.string().describe("Absolute independent UCEF workspace path"),
    scenario_id: tool.schema.string(),
    mode: tool.schema.enum(["QUICK", "STANDARD", "DEEP"]).default("STANDARD"),
  },
  async execute(args, context) {
    return invoke(context, args.workspace, [
      "analysis-start", "--scenario", args.scenario_id, "--mode", args.mode,
    ])
  },
})

export const control_next = tool({
  description: "Claim the next bounded UCEF task. The returned context is the complete task capsule.",
  args: {
    workspace: tool.schema.string(),
    run_id: tool.schema.string(),
  },
  async execute(args, context) {
    return invoke(context, args.workspace, ["analysis-next", "--run-id", args.run_id])
  },
})

export const control_status = tool({
  description: "Read compact run and task status without loading analysis evidence.",
  args: {
    workspace: tool.schema.string(),
    run_id: tool.schema.string(),
  },
  async execute(args, context) {
    return invoke(context, args.workspace, ["analysis-status", "--run-id", args.run_id])
  },
})

function submissionTool(kind: "plan" | "block" | "overview" | "gap", description: string) {
  return tool({
    description,
    args: {
      workspace: tool.schema.string().describe("Absolute independent UCEF workspace path"),
      run_id: tool.schema.string(),
      task_id: tool.schema.string(),
      payload: tool.schema.string().describe("One complete JSON object for this final artifact; never wrap in Markdown"),
    },
    async execute(args, context) {
      JSON.parse(args.payload)
      return invoke(
        context,
        args.workspace,
        ["submit-direct", "--kind", kind, "--run-id", args.run_id, "--task-id", args.task_id],
        args.payload,
      )
    },
  })
}

export const submit_plan = submissionTool(
  "plan",
  "Validate and directly persist one final ScenarioPlan. Creates the bounded block-task queue.",
)

export const submit_block = submissionTool(
  "block",
  "Validate and directly persist one reader-ready BusinessBlock. No parent-agent rewrite is required.",
)

export const submit_overview = submissionTool(
  "overview",
  "Validate and directly persist the final ScenarioOverview from stored BusinessBlocks.",
)

export const submit_gap = submissionTool(
  "gap",
  "Persist one explicit gap without creating another task.",
)
