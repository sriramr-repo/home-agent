# Muse Agent

A containerized multi-agent orchestration platform with sliding-window context compaction, out-of-band Sentinel security gates, append-only flight recorder chronicles, dynamic self-healing tool registration, and workspace taint guards.

## Features

- **Multi-Agent Architecture**: Supervisor, Code Engineer, Test Runner, and Sentinel nodes built on LangGraph.
- **Sliding-Window Compaction**: Model payload filter preserves system/user anchors and recent turns while truncating bulky intermediate observations.
- **Sentinel Security Firewall**: Intercepts high-risk operations (`run_command`, `write_file`, `edit_file`) and pauses execution (`awaiting_approval`) until explicitly authorized.
- **Multi-Tenant ACLs**: Strict sandbox boundary isolation (`/tmp/sandbox_workspace/{user_id}/{project_id}`) preventing path traversal escapes.
- **Flight Recorder Chronicle**: Append-only JSONL event stream capturing execution turns for hot-replay rehydration.
- **Dynamic Tool Hot-Loading**: Self-healing runtime tool generation via `load_generated_tool` (guarded by `MUSE_ALLOW_DYNAMIC_TOOLS=1`).
- **Workspace Taint Guard**: Mid-mutation crash detection surfacing `workspace_taint_status = "interrupted_execution"` on restart.
- **Frontend UI**: Next.js dashboard featuring architecture toggles, node badges, and taint warning banners.

## Quick Start

### 1. Run Services
```bash
docker compose up --build
```

### 2. Run Tests
```bash
docker compose exec backend pytest /tests
```

## Architecture

- **Backend**: Python 3.11, FastAPI, LangGraph, Pydantic v2.
- **Database**: PostgreSQL with `pgvector`.
- **Frontend**: Next.js 14, Tailwind CSS.
