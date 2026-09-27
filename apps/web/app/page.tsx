"use client";

import { FormEvent, useState } from "react";

type AgentState = {
  objective: string;
  status: string;
  plan: string[];
  observations: string[];
  result: string | null;
  error: string | null;
};

export default function Home() {
  const [objective, setObjective] = useState("");
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
        body: JSON.stringify({ objective }),
      });
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      setState(await response.json());
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Muse Agent</h1>
      <p>What should I accomplish?</p>
      <form onSubmit={runAgent}>
        <textarea
          name="objective"
          value={objective}
          onChange={(event) => setObjective(event.target.value)}
          placeholder="Research the AI agent market and create a report."
          rows={6}
          required
        />
        <button type="submit" disabled={loading}>
          {loading ? "Running..." : "Run Agent"}
        </button>
      </form>

      {requestError && <p role="alert">{requestError}</p>}
      {state && (
        <section>
          <h2>Agent {state.status}</h2>
          <p><strong>Objective:</strong> {state.objective}</p>
          <h3>Plan</h3>
          <ol>{state.plan.map((step) => <li key={step}>{step}</li>)}</ol>
          <h3>Result</h3>
          <p>{state.result ?? state.error}</p>
          <h3>Observations</h3>
          <ul>{state.observations.map((observation) => <li key={observation}>{observation}</li>)}</ul>
        </section>
      )}
    </main>
  );
}