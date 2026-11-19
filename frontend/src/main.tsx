import { Component, FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Source = { title: string; source: string; url: string };
type Message = { role: "user" | "assistant"; content: string; sources?: Source[] };

class AppErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return <main className="app-shell"><section className="app-error"><h1>Something went wrong</h1><p>{this.state.error.message}</p><button onClick={() => window.location.reload()}>Reload chat</button></section></main>;
    }
    return this.props.children;
  }
}

const suggestions = [
  "What projects does DarGlobal have?",
  "Find properties in Riyadh.",
  "What information is available about properties in Dubai?",
];
const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const endOfMessages = useRef<HTMLDivElement>(null);

  useEffect(() => endOfMessages.current?.scrollIntoView({ behavior: "smooth" }), [messages, loading]);

  async function sendMessage(event?: FormEvent, suggested?: string) {
    event?.preventDefault();
    const question = (suggested ?? input).trim();
    if (!question || loading) return;
    const nextMessages = [...messages, { role: "user" as const, content: question }];
    setMessages(nextMessages);
    setInput("");
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`${apiUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, history: messages.map(({ role, content }) => ({ role, content })) }),
      });
      if (!response.ok) throw new Error("The server could not process your question.");
      const data: unknown = await response.json();
      const answer = typeof (data as { answer?: unknown }).answer === "string"
        ? (data as { answer: string }).answer
        : "The server returned an invalid chat response.";
      const sources = Array.isArray((data as { sources?: unknown }).sources)
        ? (data as { sources: unknown[] }).sources.filter(isValidSource)
        : [];
      setMessages([...nextMessages, { role: "assistant", content: answer, sources }]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Something went wrong. Please try again.");
    } finally { setLoading(false); }
  }

  return <main className="app-shell">
    <section className="chat-card">
      <header><div><h1>Real Estate AI Assistant</h1><p>Explore property information from DarGlobal &amp; Wasalt</p></div><button className="clear" onClick={() => { setMessages([]); setError(""); }}>Clear chat</button></header>
      <div className="conversation">
        {messages.length === 0 && <div className="empty"><h2>How can I help?</h2><p>Ask about the public property information collected from DarGlobal and Wasalt.</p><div className="suggestions">{suggestions.map((question) => <button key={question} onClick={() => sendMessage(undefined, question)}>{question}</button>)}</div></div>}
        {messages.map((message, index) => <article key={index} className={`message ${message.role}`}><div className="label">{message.role === "user" ? "You" : "Assistant"}</div><p>{message.content}</p>{message.sources && message.sources.length > 0 && <div className="sources"><span>Sources</span>{message.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.source}: {source.title}</a>)}</div>}</article>)}
        {loading && <article className="message assistant"><div className="label">Assistant</div><p className="loading">Searching collected property information…</p></article>}
        <div ref={endOfMessages} />
      </div>
      {error && <p className="error">{error}</p>}
      <form onSubmit={sendMessage}><input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about a project, location, or property…" aria-label="Your question" /><button disabled={loading || !input.trim()}>{loading ? "Sending…" : "Send"}</button></form>
    </section>
  </main>;
}

function isValidSource(value: unknown): value is Source {
  if (!value || typeof value !== "object") return false;
  const source = value as Record<string, unknown>;
  return ["title", "source", "url"].every((key) => typeof source[key] === "string");
}

createRoot(document.getElementById("root")!).render(<AppErrorBoundary><App /></AppErrorBoundary>);

