"use client";

import { FormEvent, useState } from "react";

type AgentState = {
  objective: string;
  status: string;
  plan: string[];
  observations: string[];
  result: string | null;
  error: string | null;
  workspace_taint_status?: string | null;
};

export default function Home() {
  const [objective, setObjective] = useState("");
  const [architectureMode, setArchitectureMode] = useState<"single_agent" | "multi_agent">("single_agent");
  const [state, setState] = useState<AgentState | null>(null);
  const [loading, setLoading] = useState(false);
  const [requestError, setRequestError] = useState("");

  async function runAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setRequestError("");
    try {
      const response = await fetch("http://localhost:8000/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          objective,
          use_multi_agent: architectureMode === "multi_agent",
        }),
      });
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      setState(await response.json());
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  function renderObservation(obs: string) {
    if (obs.includes("Supervisor") || obs.includes("planner")) {
      return <span>👑 <strong>[Supervisor]</strong> {obs}</span>;
    }
    if (obs.includes("engineer") || obs.includes("executor")) {
      return <span>📝 <strong>[Code Engineer]</strong> {obs}</span>;
    }
    if (obs.includes("verifier") || obs.includes("tester")) {
      return <span>🔧 <strong>[Test Runner]</strong> {obs}</span>;
    }
    if (obs.includes("sentinel")) {
      return <span>🛑 <strong>[Sentinel Guard]</strong> {obs}</span>;
    }
    return <span>{obs}</span>;
  }

  return (
    <main style={{ padding: "2rem", maxWidth: "800px", margin: "0 auto", fontFamily: "sans-serif" }}>
      <h1>Muse Agent</h1>
      <p>What should I accomplish?</p>
      <form onSubmit={runAgent}>
        <div style={{ marginBottom: "1rem" }}>
          <label style={{ marginRight: "1rem" }}>
            <input
              type="radio"
              name="arch"
              value="single_agent"
              checked={architectureMode === "single_agent"}
              onChange={() => setArchitectureMode("single_agent")}
            />{" "}
            Single Agent
          </label>
          <label>
            <input
              type="radio"
              name="arch"
              value="multi_agent"
              checked={architectureMode === "multi_agent"}
              onChange={() => setArchitectureMode("multi_agent")}
            />{" "}
            Multi-Agent Supervisor
          </label>
        </div>
        <textarea
          name="objective"
          value={objective}
          onChange={(event) => setObjective(event.target.value)}
          placeholder="Research the AI agent market and create a report."
          rows={6}
          required
          style={{ width: "100%", marginBottom: "1rem" }}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Running..." : "Run Agent"}
        </button>
      </form>

      {requestError && <p role="alert" style={{ color: "red" }}>{requestError}</p>}
      {state && (
        <section style={{ marginTop: "2rem" }}>
          {state.workspace_taint_status === "interrupted_execution" && (
            <div style={{ border: "2px solid #ff4d4f", backgroundColor: "#fff2f0", padding: "1rem", marginBottom: "1rem", borderRadius: "4px" }}>
              <p style={{ margin: 0, color: "#cf1322", fontWeight: "bold" }}>
                ⚠️ Alert: Workspace Interruption Detected. Muse has successfully rehydrated from an unsafe execution crash point and is awaiting your instruction.
              </p>
            </div>
          )}
          <h2>Agent {state.status}</h2>
          <p><strong>Objective:</strong> {state.objective}</p>
          <h3>Plan</h3>
          <ol>{state.plan.map((step) => <li key={step}>{step}</li>)}</ol>
          <h3>Result</h3>
          <p>{state.result ?? state.error}</p>
          <h3>Observations</h3>
          <ul>{state.observations.map((obs) => <li key={obs}>{renderObservation(obs)}</li>)}</ul>
        </section>
      )}
    </main>
  );
}
