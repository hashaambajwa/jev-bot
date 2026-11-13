# Architecture and evaluation contract

## Problem

Tool-using agents produce *actions*, not just text. A model can produce a fluent final answer while the action path breached an approval boundary, exceeded a spending limit or silently dropped a tool error. An evaluator that checks only the final answer misses these failures.

Jev splits the problem into two independent layers:

1. **Decision gate (before the tool call):** application-owned code submits a proposed tool call and trusted runtime state to a deterministic policy evaluator. A denied proposal must not reach the dispatcher.
2. **Trajectory grader (after the run):** an append-only JSONL trace is checked for internal consistency, then graded against explicit task assertions. Reports can be compared across revisions using identical case IDs.

    Agent/model --> tool proposal --> Jev policy gate --> tool dispatcher
                                       | denied         |
                                       v                v
                                   error/approval   trace events
                                                        |
                                           Jev trace validator
                                                        |
                                           suite assertion grader
                                                        |
                                        baseline/candidate diff
                                                        |
                                               CI gate

## Event contract v1

Each JSONL line is a complete JSON object with a single run_id and contiguous integer step from 0. Accepted event kinds:

- `tool_call`: required `call_id`, `tool`; optional `arguments` object, `approved` boolean, non-negative `cost_usd` and `latency_ms`.
- `tool_result`: required `call_id` matching a previous call, and boolean `success`. Optional `output`.
- `final`: required string `answer`; must be last.

A trace is rejected when a call lacks a result, when IDs repeat, when steps are missing, or when events follow a final answer. The reader caps file size (2 MB) and event count (10,000), providing bounded memory for expected fixture use.

**Important:** the event structure is a local developer contract, not the OpenTelemetry semantic-conventions schema. An adapter is needed to use telemetry from any particular framework.

## Policy contract v1

All configuration keys are explicitly validated. An unknown field is an error rather than silently ignored. Tool names are exact-match and **deny-by-default**. Rejections return stable, machine-readable reason codes; missing or malformed input raises a PolicyError that the caller must handle by denying execution.

- allowed_tools: exact allowlist
- approval_required: subset of allowed_tools
- forbidden_argument_keys: recursively rejected JSON argument keys (case insensitive)
- max_tool_calls: cumulative tool-invocation budget
- max_total_cost_usd: cumulative estimated cost budget

An approval flag in an untrusted model output is **not** proof of human approval. The surrounding application must supply an approval value derived from a trusted approval workflow. Similarly, the application must pass trusted prior usage and cannot rely on the model to report actual cost.

## Grading

Each case specifies a trace file plus any subset of:

- must_call / must_not_call
- exact tool_sequence
- final_contains (case-insensitive substrings)
- max_tool_calls / max_cost_usd / max_latency_ms
- require_successful_tools

A case passes only if every assertion and every configured policy check passes. Invalid traces count as failed cases. Metrics are totals and interpolated p50/p95 latencies over supplied traces, not causal performance claims. An eval suite has at most 500 cases and resolves relative trace paths inside the suite directory, rejecting traversal.

Paired report comparisons reject disjoint case ID sets and list individual regressions. They **do not** infer statistical significance or establish real-model benchmark quality.

## Threat model and limitations

Jev defends against some application-level mistakes, malformed input and rule violations. It does not:

- authenticate the party who emitted a trace
- stop a caller that bypasses the gate
- detect semantic prompt injection inside arbitrary tool outputs
- guarantee tool-return truth, task correctness, or external authorization
- measure real spend if cost_estimate_usd or cost_usd is inaccurate
- provide production-grade multi-tenant persistence, secrets protection, or tamper-proof logs

Treat logs as sensitive data. Avoid capturing raw credentials, private prompts and user data. Human approval must be enforced by a separate trusted authorization system. Use provider-side permissions, budget limits and approvals in addition to Jev.

## Extension points

A framework adapter can map actual model tool events into event contract v1 without importing the framework into Jev's core. Further work includes an OpenTelemetry GenAI import adapter, trace provenance signatures, integration-time policy hooks, and evaluations with live models on held-out tasks.
