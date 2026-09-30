import { useMemo, useRef, useState } from "react";
import {
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from "recharts";

type ResultRow = {
  label: string;
  value: string | number | null;
};

type AnalysisResponse = {
  question: string;
  file_name: string;
  intent: Record<string, unknown>;
  confidence: number;
  confidence_label: string;
  confidence_reasons: string[];
  answer: string;
  result: ResultRow[];
  chart_type: "bar" | "pie" | "line" | "hist" | "none";
};

const API_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000/api/analyze";

const EXAMPLES = [
  "What is total revenue in 2024?",
  "Top 5 product lines by trade sales dollars in 2024",
  "Top 5 product segments according to trade sales dollars",
  "Top 5 product lines in Building Supply",
  "Bottom 5 trade sales by state"
];

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const chartData = useMemo(
    () =>
      response?.result
        .map((row) => ({
          name: String(row.label).slice(0, 28),
          value:
            typeof row.value === "number"
              ? row.value
              : Number(String(row.value).replace(/[$,M]/g, "")) || 0
        }))
        .filter((row) => Number.isFinite(row.value)) ?? [],
    [response]
  );

  async function analyze() {
    if (!file) {
      setError("Please upload a sales Excel file first.");
      return;
    }

    if (!question.trim()) {
      setError("Please enter a business question.");
      return;
    }

    setLoading(true);
    setError("");
    setResponse(null);

    try {
      const form = new FormData();
      form.append("file", file);
      form.append("question", question.trim());

      const res = await fetch(API_URL, {
        method: "POST",
        body: form
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "The analytics request failed.");
      }

      setResponse(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to connect to the analytics engine."
      );
    } finally {
      setLoading(false);
    }
  }

  function chooseFile(selected: File | undefined) {
    if (!selected) return;
    const valid =
      selected.name.toLowerCase().endsWith(".xlsx") ||
      selected.name.toLowerCase().endsWith(".xls");

    if (!valid) {
      setError("Please upload an Excel .xlsx or .xls file.");
      return;
    }

    setFile(selected);
    setError("");
    setResponse(null);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          <span>GenAI Sales Analytics</span>
        </div>
        <span className="status-pill">AI + Deterministic Analytics</span>
      </header>

      <main className="container">
        <section className="hero">
          <p className="eyebrow">NATURAL LANGUAGE ANALYTICS</p>
          <h1>
            Ask questions.
            <br />
            <span>Get measurable answers.</span>
          </h1>
          <p className="hero-copy">
            Upload a sales Excel file and ask a business question in plain
            English. The system converts the question into a structured
            analytical intent, computes the result deterministically, and
            generates a concise explanation.
          </p>
        </section>

        <section className="workspace">
          <div className="panel input-panel">
            <div className="panel-heading">
              <div>
                <p className="step">01</p>
                <h2>Upload sales data</h2>
              </div>
              <span className="file-type">.XLSX / .XLS</span>
            </div>

            <button
              className="upload-zone"
              onClick={() => inputRef.current?.click()}
            >
              <div className="upload-icon">↑</div>
              <strong>
                {file ? file.name : "Choose your sales Excel file"}
              </strong>
              <span>
                {file
                  ? `${(file.size / 1024 / 1024).toFixed(2)} MB selected`
                  : "Click to browse from your computer"}
              </span>
            </button>

            <input
              ref={inputRef}
              type="file"
              accept=".xlsx,.xls"
              hidden
              onChange={(e) => chooseFile(e.target.files?.[0])}
            />

            <div className="question-header">
              <div>
                <p className="step">02</p>
                <h2>Ask a question</h2>
              </div>
            </div>

            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Example: What are the top 5 product lines by trade sales dollars in 2024?"
              rows={6}
            />

            <div className="examples">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  onClick={() => setQuestion(example)}
                  className="example-chip"
                >
                  {example}
                </button>
              ))}
            </div>

            <button
              className="analyze-button"
              onClick={analyze}
              disabled={loading}
            >
              {loading ? "Analyzing..." : "Analyze sales data →"}
            </button>

            {error && <div className="error">{error}</div>}
          </div>

          <div className="panel answer-panel">
            <div className="panel-heading">
              <div>
                <p className="step">03</p>
                <h2>Generated answer</h2>
              </div>

              {response && (
                <span
                  className={`confidence ${response.confidence_label.toLowerCase()}`}
                >
                  {response.confidence_label} confidence ·{" "}
                  {Math.round(response.confidence * 100)}%
                </span>
              )}
            </div>

            {!response && !loading && (
              <div className="empty-state">
                <div className="empty-icon">✦</div>
                <h3>Your answer will appear here</h3>
                <p>
                  Upload a file and ask a question to run the analytics engine.
                </p>
              </div>
            )}

            {loading && (
              <div className="empty-state">
                <div className="loader" />
                <h3>Analyzing your data...</h3>
                <p>
                  Parsing intent, running deterministic calculations, and
                  preparing the explanation.
                </p>
              </div>
            )}

            {response && (
              <div className="results">
                <div className="answer-box">
                  <p className="result-label">ANSWER</p>
                  <p>{response.answer}</p>
                </div>

                {response.result.length > 0 && (
                  <>
                    <div className="result-table">
                      <div className="result-table-head">
                        <span>Category</span>
                        <span>Value</span>
                      </div>

                      {response.result.map((row, index) => (
                        <div className="result-row" key={`${row.label}-${index}`}>
                          <span>{row.label}</span>
                          <strong>{String(row.value ?? "—")}</strong>
                        </div>
                      ))}
                    </div>

                    {response.chart_type !== "none" && chartData.length > 0 && (
                      <div className="chart-card">
                        <p className="result-label">VISUALIZATION</p>

                        <div className="chart">
                          {response.chart_type === "pie" ? (
                            <ResponsiveContainer width="100%" height={300}>
                              <PieChart>
                                <Pie
                                  data={chartData}
                                  dataKey="value"
                                  nameKey="name"
                                  cx="50%"
                                  cy="50%"
                                  outerRadius={100}
                                  label
                                >
                                  {chartData.map((_, index) => (
                                    <Cell
                                      key={index}
                                      fill={`hsl(${195 + index * 25} 80% ${
                                        62 - index * 3
                                      }%)`}
                                    />
                                  ))}
                                </Pie>
                                <Tooltip />
                              </PieChart>
                            </ResponsiveContainer>
                          ) : (
                            <ResponsiveContainer width="100%" height={300}>
                              <BarChart data={chartData}>
                                <CartesianGrid
                                  strokeDasharray="3 3"
                                  opacity={0.15}
                                />
                                <XAxis
                                  dataKey="name"
                                  angle={-25}
                                  textAnchor="end"
                                  height={80}
                                />
                                <YAxis />
                                <Tooltip />
                                <Bar dataKey="value" fill="#7dd3fc" />
                              </BarChart>
                            </ResponsiveContainer>
                          )}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {response.confidence_reasons.length > 0 && (
                  <div className="confidence-box">
                    <p className="result-label">CONFIDENCE NOTES</p>
                    <ul>
                      {response.confidence_reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        <section className="architecture">
          <p className="eyebrow">HOW IT WORKS</p>
          <div className="architecture-grid">
            <div>
              <span>01</span>
              <h3>Natural language</h3>
              <p>Ask a business question without writing SQL or Python.</p>
            </div>
            <div>
              <span>02</span>
              <h3>AI intent parsing</h3>
              <p>
                GPT converts the question into a structured analytical intent.
              </p>
            </div>
            <div>
              <span>03</span>
              <h3>Deterministic engine</h3>
              <p>
                Pandas performs the actual calculations rather than the LLM.
              </p>
            </div>
            <div>
              <span>04</span>
              <h3>Business explanation</h3>
              <p>
                The result is returned with a concise, decision-oriented
                explanation.
              </p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
