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
    {
      stdin: "pipe",
      stdout: "pipe",
      stderr: "pipe",
      env: {
        ...process.env,
        PYTHONUTF8: "1",
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
      },
    },
  )
  if (payload !== undefined) {
    proc.stdin.write(new TextEncoder().encode(payload))
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

export const analysis_start = tool({
  description: "Start or resume one adaptive UCEF exploration. The main model owns business understanding; runtime persists facts, controls context, and generates HTML.",
  args: {
    workspace: tool.schema.string().describe("Absolute independent UCEF workspace path"),
    scenario_id: tool.schema.string(),
    goal: tool.schema.string().optional().describe("Optional analysis focus or business question"),
    priority_fields: tool.schema.string().optional().describe("Optional comma-separated P0 field names"),
    context_target_tokens: tool.schema.number().optional(),
    total_token_budget: tool.schema.number().optional(),
  },
  async execute(args, context) {
    const command = ["session-start", "--scenario", args.scenario_id]
    if (args.goal) command.push("--goal", args.goal)
    if (args.priority_fields) command.push("--priority-fields", args.priority_fields)
    if (args.context_target_tokens) command.push("--context-target", String(args.context_target_tokens))
    if (args.total_token_budget) command.push("--token-budget", String(args.total_token_budget))
    return invoke(context, args.workspace, command)
  },
})

export const analysis_record = tool({
  description: "Persist one small meaningful business milestone: systems, modules, decisions/branches, fields/events, external interactions, persistence, evidence, or gaps. Returns a compact receipt and refreshes adaptive HTML.",
  args: {
    workspace: tool.schema.string(),
    session_id: tool.schema.string(),
    facts: tool.schema.object({}).passthrough().describe("Flexible semantic delta; include only newly understood business facts and a brief summary"),
  },
  async execute(args, context) {
    return invoke(
      context,
      args.workspace,
      ["session-delta", "--session-id", args.session_id],
      JSON.stringify(args.facts),
    )
  },
})

export const analysis_context = tool({
  description: "Recall a bounded global digest plus facts relevant to the current symbol, field, decision, or configuration. Never load the full persisted graph by default.",
  args: {
    workspace: tool.schema.string(),
    session_id: tool.schema.string(),
    focus: tool.schema.string().optional(),
    fields: tool.schema.string().optional().describe("Optional comma-separated field names"),
    symbols: tool.schema.string().optional().describe("Optional comma-separated Java symbols"),
    max_tokens: tool.schema.number().optional(),
  },
  async execute(args, context) {
    const command = ["session-context", "--session-id", args.session_id]
    if (args.focus) command.push("--focus", args.focus)
    if (args.fields) command.push("--field", args.fields)
    if (args.symbols) command.push("--symbol", args.symbols)
    if (args.max_tokens) command.push("--max-tokens", String(args.max_tokens))
    return invoke(context, args.workspace, command)
  },
})

export const analysis_status = tool({
  description: "Read concise adaptive exploration progress, semantic milestone summaries, remaining configuration gaps, and field/branch coverage.",
  args: { workspace: tool.schema.string(), session_id: tool.schema.string() },
  async execute(args, context) {
    return invoke(context, args.workspace, ["session-status", "--session-id", args.session_id])
  },
})

export const analysis_finish = tool({
  description: "Finish an adaptive exploration with a concise business conclusion. Existing explicit gaps remain visible and automatically mark the result partial.",
  args: {
    workspace: tool.schema.string(),
    session_id: tool.schema.string(),
    summary: tool.schema.string(),
    status: tool.schema.enum(["COMPLETE", "PARTIAL", "STOPPED"]).default("COMPLETE"),
  },
  async execute(args, context) {
    return invoke(context, args.workspace, [
      "session-finish", "--session-id", args.session_id,
      "--summary", args.summary, "--status", args.status,
    ])
  },
})

export const knowledge_query = tool({
  description: "Search compact shared business entities by scenario, type, name, symbol, table, configuration key, or stable entity identity.",
  args: {
    workspace: tool.schema.string(),
    scenario_id: tool.schema.string().optional(),
    entity_type: tool.schema.string().optional(),
    search: tool.schema.string().optional(),
    entity_id: tool.schema.string().optional(),
    limit: tool.schema.number().optional(),
  },
  async execute(args, context) {
    const command = ["graph-query"]
    if (args.scenario_id) command.push("--scenario", args.scenario_id)
    if (args.entity_type) command.push("--type", args.entity_type.toUpperCase())
    if (args.search) command.push("--search", args.search)
    if (args.entity_id) command.push("--entity", args.entity_id)
    if (args.limit) command.push("--limit", String(args.limit))
    return invoke(context, args.workspace, command)
  },
})

export const knowledge_lineage = tool({
  description: "Return one field journey with ordinary DTO copies collapsed and meaningful transformations, persistence, external requests, and response consumption preserved.",
  args: {
    workspace: tool.schema.string(),
    scenario_id: tool.schema.string(),
    field: tool.schema.string(),
  },
  async execute(args, context) {
    return invoke(context, args.workspace, [
      "field-lineage", "--scenario", args.scenario_id, "--field", args.field,
    ])
  },
})

export const configuration_resolve = tool({
  description: "Apply an explicitly verified configuration value, ideally from future intranet PADB evidence. Updates affected branch selection and HTML; never guess unavailable production values.",
  args: {
    workspace: tool.schema.string(),
    scenario_id: tool.schema.string(),
    key: tool.schema.string(),
    value: tool.schema.string().describe("Confirmed value; JSON scalars are accepted"),
    environment: tool.schema.string().default("prod"),
    evidence: tool.schema.string().optional().describe("PADB lookup or other verifiable source reference"),
  },
  async execute(args, context) {
    const command = [
      "config-resolve", "--scenario", args.scenario_id,
      "--key", args.key, "--value", args.value, "--environment", args.environment,
    ]
    if (args.evidence) command.push("--evidence", args.evidence)
    return invoke(context, args.workspace, command)
  },
})

export const entity_rename = tool({
  description: "Rename a shared business system, module, decision, field, or table once and deterministically refresh every scenario and perspective that references it.",
  args: {
    workspace: tool.schema.string(),
    entity_id: tool.schema.string(),
    name: tool.schema.string(),
  },
  async execute(args, context) {
    return invoke(context, args.workspace, [
      "entity-rename", "--entity-id", args.entity_id, "--name", args.name,
    ])
  },
})

// Compatibility-only v0.10 tools. The UCEF 1.0 primary agent never schedules
// planner/block/finalizer queues; old persisted runs remain readable.
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
