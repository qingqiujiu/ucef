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

export const workspace_bootstrap = tool({
  description: "Create or repair an independent UCEF workspace from bundled defaults. The Agent does not need to read initialization scripts.",
  args: {
    workspace: tool.schema.string().describe("Absolute directory outside every Java source tree"),
  },
  async execute(args, context) {
    return invoke(context, args.workspace, ["bootstrap"])
  },
})

export const source_register = tool({
  description: "Register one Java project as a read-only UCEF source. Runtime rejects workspace/source nesting.",
  args: {
    workspace: tool.schema.string(),
    source_id: tool.schema.string().describe("Stable short source identity"),
    source_path: tool.schema.string().describe("Absolute Java project path"),
    repository: tool.schema.string().optional(),
    revision: tool.schema.string().optional(),
    role: tool.schema.string().optional(),
  },
  async execute(args, context) {
    const command = ["source-add", "--source-id", args.source_id, "--path", args.source_path]
    if (args.repository) command.push("--repository", args.repository)
    if (args.revision) command.push("--revision", args.revision)
    if (args.role) command.push("--role", args.role)
    return invoke(context, args.workspace, command)
  },
})

export const source_list = tool({
  description: "List compact source registration status without reading source files.",
  args: { workspace: tool.schema.string() },
  async execute(args, context) {
    return invoke(context, args.workspace, ["source-list"])
  },
})

export const scenario_register = tool({
  description: "Persist one Scenario from typed business fields. Runtime constructs the JSON; do not create or read a scenario file.",
  args: {
    workspace: tool.schema.string(),
    scenario_id: tool.schema.string().describe("Stable ID beginning with SCN-"),
    name: tool.schema.string(),
    business_operation: tool.schema.string(),
    business_goal: tool.schema.string(),
    trigger_kind: tool.schema.string(),
    trigger_symbol: tool.schema.string(),
    input_type: tool.schema.string().default("UNKNOWN"),
    source_ids: tool.schema.string().describe("Comma-separated registered source IDs"),
    environment: tool.schema.string().default("prod"),
    config_snapshot_id: tool.schema.string().optional(),
    expected_outcome: tool.schema.string(),
    critical_fields: tool.schema.string().optional().describe("Optional comma-separated P0 field names"),
  },
  async execute(args, context) {
    const sourceIds = args.source_ids.split(",").map((value) => value.trim()).filter(Boolean)
    const criticalFields = (args.critical_fields || "").split(",").map((value) => value.trim()).filter(Boolean)
    const scenario = {
      scenario_id: args.scenario_id,
      name: args.name,
      business_operation: args.business_operation,
      business_goal: args.business_goal,
      trigger: { kind: args.trigger_kind, symbol: args.trigger_symbol, input_type: args.input_type },
      scope: {
        source_ids: sourceIds,
        environment: args.environment,
        config_snapshot_id: args.config_snapshot_id || "UNKNOWN",
        request_constraints: {},
      },
      expected_outcome: args.expected_outcome,
      critical_fields: criticalFields,
      status: "ACTIVE",
    }
    return invoke(context, args.workspace, ["scenario-put"], JSON.stringify(scenario))
  },
})

export const artifact_register = tool({
  description: "Register one UTF-8 JSON file as a content-addressed redacted artifact and rebuild the site. Never return the artifact body to the Agent.",
  args: {
    workspace: tool.schema.string(),
    file: tool.schema.string().describe("Absolute JSON snapshot path, or path inside the UCEF workspace"),
    scenario_id: tool.schema.string().optional(),
    source_id: tool.schema.string().optional(),
    environment: tool.schema.string().optional(),
    snapshot_id: tool.schema.string().optional(),
    kind: tool.schema.string().default("CONFIG_JSON"),
    redact_keys: tool.schema.string().optional().describe("Optional comma-separated additional keys to redact"),
  },
  async execute(args, context) {
    const command = ["artifact-add", "--file", args.file, "--kind", args.kind]
    if (args.scenario_id) command.push("--scenario", args.scenario_id)
    if (args.source_id) command.push("--source-id", args.source_id)
    if (args.environment) command.push("--environment", args.environment)
    if (args.snapshot_id) command.push("--snapshot", args.snapshot_id)
    for (const key of (args.redact_keys || "").split(",").map((value) => value.trim()).filter(Boolean)) {
      command.push("--redact-key", key)
    }
    return invoke(context, args.workspace, command)
  },
})

export const artifact_list = tool({
  description: "List artifact metadata only; never load stored JSON content into Agent context.",
  args: {
    workspace: tool.schema.string(),
    scenario_id: tool.schema.string().optional(),
  },
  async execute(args, context) {
    const command = ["artifact-list"]
    if (args.scenario_id) command.push("--scenario", args.scenario_id)
    return invoke(context, args.workspace, command)
  },
})

export const site_build = tool({
  description: "Deterministically rebuild the UCEF HTML site from persisted facts without asking an Agent to write HTML.",
  args: { workspace: tool.schema.string() },
  async execute(args, context) {
    return invoke(context, args.workspace, ["site"])
  },
})

function submissionTool(kind: "plan" | "block" | "overview" | "gap", description: string) {
  return tool({
    description,
    args: {
      workspace: tool.schema.string().describe("Absolute independent UCEF workspace path"),
      run_id: tool.schema.string(),
      task_id: tool.schema.string(),
      payload: tool.schema.object({}).passthrough().describe("Object made by filling context.output_contract.payload_template; omit runtime-injected IDs"),
    },
    async execute(args, context) {
      return invoke(
        context,
        args.workspace,
        ["submit-direct", "--kind", kind, "--run-id", args.run_id, "--task-id", args.task_id],
        JSON.stringify(args.payload),
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
