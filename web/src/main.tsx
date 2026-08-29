import React, { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Material = {
  id: string; name: string; description: string; category: string;
  default_prompt_lang: string; default_answer_lang: string; is_enabled: boolean;
  question_count: number; due_count: number;
};
type ImportSource = {
  id: string; material_id: string; name: string; kind: string; url: string;
  is_enabled: boolean; last_sync_status: string; last_sync_error: string; last_synced_at?: string;
};
type Question = {
  id: string; material_id: string; prompt: string; answer: string; explanation: string;
  question_type: string; prompt_lang: string; answer_lang: string; choices: string[]; tags: string[];
  mastery?: string; due_at?: string;
};
type Stats = {
  active_questions: number; learned_questions: number; due_questions: number;
  reviews_24h: number; accuracy_24h: number; mastery: Record<string, number>;
};
type StudySession = { session_id: string; total_pool: number; questions: Question[] };
type Page = "dashboard" | "study" | "materials" | "questions" | "mcp";

const API = "/api/v1";

function token() { return localStorage.getItem("ponkan.apiToken") || ""; }
async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (init.body) headers.set("Content-Type", "application/json");
  if (token()) headers.set("Authorization", `Bearer ${token()}`);
  const response = await fetch(`${API}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || body.error || response.statusText);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

function speak(text: string, lang: string) {
  if (!("speechSynthesis" in window)) return;
  const utterance = new SpeechSynthesisUtterance(text);
  if (lang) utterance.lang = lang;
  speechSynthesis.cancel();
  speechSynthesis.speak(utterance);
}

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [materials, setMaterials] = useState<Material[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = () => setRefreshKey(x => x + 1);

  useEffect(() => {
    Promise.all([api<Material[]>("/materials"), api<Stats>("/stats/summary")])
      .then(([m, s]) => { setMaterials(m); setStats(s); setError(""); })
      .catch(e => setError(String(e.message || e)));
  }, [refreshKey]);

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">P</span><div><b>Ponkan</b><small>Study platform</small></div></div>
      <nav>
        <Nav page="dashboard" current={page} onClick={setPage}>概要</Nav>
        <Nav page="study" current={page} onClick={setPage}>学習</Nav>
        <Nav page="materials" current={page} onClick={setPage}>教材</Nav>
        <Nav page="questions" current={page} onClick={setPage}>問題</Nav>
        <Nav page="mcp" current={page} onClick={setPage}>MCP / 設定</Nav>
      </nav>
      <div className="sidebar-foot"><span className="status-dot" /> self-hosted</div>
    </aside>
    <main>
      <header className="topbar">
        <div><h1>{title(page)}</h1><p>{subtitle(page)}</p></div>
        <button className="ghost" onClick={refresh}>更新</button>
      </header>
      {error && <div className="alert">{error}</div>}
      {page === "dashboard" && <Dashboard stats={stats} materials={materials} onStudy={() => setPage("study")} />}
      {page === "study" && <Study materials={materials} onReview={refresh} />}
      {page === "materials" && <Materials materials={materials} refresh={refresh} />}
      {page === "questions" && <Questions materials={materials} refresh={refresh} />}
      {page === "mcp" && <McpSettings />}
    </main>
    <div className="mobile-nav">
      {(["dashboard", "study", "materials", "questions", "mcp"] as Page[]).map(p =>
        <button key={p} className={page === p ? "active" : ""} onClick={() => setPage(p)}>{shortTitle(p)}</button>
      )}
    </div>
  </div>;
}

function Nav({ page, current, onClick, children }: { page: Page; current: Page; onClick: (p: Page) => void; children: React.ReactNode }) {
  return <button className={page === current ? "nav active" : "nav"} onClick={() => onClick(page)}>{children}</button>;
}
function title(p: Page) { return ({ dashboard: "概要", study: "学習", materials: "教材", questions: "問題バンク", mcp: "MCP / 設定" })[p]; }
function shortTitle(p: Page) { return ({ dashboard: "概要", study: "学習", materials: "教材", questions: "問題", mcp: "MCP" })[p]; }
function subtitle(p: Page) { return ({ dashboard: "学習状況を確認します。", study: "複数教材を混ぜてSRSで復習します。", materials: "教材と外部データソースを管理します。", questions: "言語や分野に依存しない問題を管理します。", mcp: "LLM連携とローカル設定を管理します。" })[p]; }

function Dashboard({ stats, materials, onStudy }: { stats: Stats | null; materials: Material[]; onStudy: () => void }) {
  const accuracy = stats ? Math.round(stats.accuracy_24h * 100) : 0;
  return <section className="stack">
    <div className="hero">
      <div><span className="eyebrow">TODAY</span><h2>{stats?.due_questions ?? 0} 問が復習待ち</h2><p>教材を横断して、忘れかけている問題から優先します。</p></div>
      <button className="primary" onClick={onStudy}>学習を始める</button>
    </div>
    <div className="metrics">
      <Metric label="有効な問題" value={stats?.active_questions ?? 0} />
      <Metric label="学習済み" value={stats?.learned_questions ?? 0} />
      <Metric label="24hレビュー" value={stats?.reviews_24h ?? 0} />
      <Metric label="24h正答率" value={`${accuracy}%`} />
    </div>
    <div className="panel"><div className="panel-title"><h3>教材</h3><span>{materials.length} materials</span></div>
      <div className="material-grid">{materials.map(m => <div className="material-card" key={m.id}>
        <div className="material-head"><span className="pill">{m.category}</span><span className="due">{m.due_count} due</span></div>
        <h4>{m.name}</h4><p>{m.description || "説明なし"}</p>
        <div className="material-meta"><span>{m.question_count} 問</span><span>{m.default_prompt_lang || "-"} → {m.default_answer_lang || "-"}</span></div>
      </div>)}</div>
    </div>
  </section>;
}
function Metric({ label, value }: { label: string; value: string | number }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }

function Study({ materials, onReview }: { materials: Material[]; onReview: () => void }) {
  const [selected, setSelected] = useState<string[]>(materials.map(m => m.id));
  const [limit, setLimit] = useState(20);
  const [session, setSession] = useState<StudySession | null>(null);
  const [queue, setQueue] = useState<Question[]>([]);
  const [current, setCurrent] = useState<Question | null>(null);
  const [startedAt, setStartedAt] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [feedback, setFeedback] = useState<{ correct: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!current && queue.length) {
      setCurrent(queue[0]); setQueue(q => q.slice(1)); setStartedAt(performance.now());
      setRevealed(false); setFeedback(null);
    }
  }, [queue, current]);
  useEffect(() => {
    if (!selected.length && materials.length) setSelected(materials.map(m => m.id));
  }, [materials]);

  const start = async () => {
    if (!selected.length) return;
    setBusy(true);
    try {
      const next = await api<StudySession>("/study/sessions", {
        method: "POST", body: JSON.stringify({ material_ids: selected, limit })
      });
      setSession(next); setCurrent(null); setQueue(next.questions); setFeedback(null);
    } finally { setBusy(false); }
  };
  const record = async (rating: number, correct: boolean) => {
    if (!current || !session) return;
    const responseMs = Math.max(0, Math.round(performance.now() - startedAt));
    await api("/reviews", {
      method: "POST",
      body: JSON.stringify({
        question_id: current.id, session_id: session.session_id, rating,
        response_ms: responseMs, mode: current.choices.length ? "choice" : "card"
      })
    });
    setFeedback({ correct, text: correct ? "正解" : `正解: ${current.answer}` });
    if (!correct) setQueue(items => {
      const next = [...items]; next.splice(Math.min(3, next.length), 0, current); return next;
    });
    onReview();
  };
  const choose = async (choice: string) => {
    if (!current || feedback) return;
    const correct = choice === current.answer;
    const ms = performance.now() - startedAt;
    const rating = correct ? (ms < 1800 ? 4 : ms < 5500 ? 3 : 2) : 1;
    await record(rating, correct);
  };
  const next = () => { setCurrent(null); setFeedback(null); setRevealed(false); };

  if (session && !current && queue.length === 0) return <div className="center-card"><span className="eyebrow">SESSION COMPLETE</span><h2>学習終了</h2><p>このセッションの問題をすべて処理しました。</p><button className="primary" onClick={() => setSession(null)}>もう一度</button></div>;
  if (session && current) return <div className="study-wrap">
    <div className="study-progress"><span>{current.tags.join(" / ") || "question"}</span><span>残り {queue.length + 1}</span></div>
    <div className="study-card">
      <div className="study-actions"><span className={`mastery ${current.mastery || "weak"}`}>{current.mastery || "weak"}</span>{current.prompt_lang && <button className="icon" onClick={() => speak(current.prompt, current.prompt_lang)}>音声</button>}</div>
      <h2>{current.prompt}</h2>
      {current.choices.length > 0 ? <div className="choices">{current.choices.map(choice => <button disabled={!!feedback} key={choice} onClick={() => choose(choice)} className={feedback && choice === current.answer ? "correct" : ""}>{choice}</button>)}</div> :
        <div>{!revealed ? <button className="primary wide" onClick={() => setRevealed(true)}>答えを見る</button> : <div className="answer-box"><strong>{current.answer}</strong><div className="ratings"><button disabled={!!feedback} onClick={() => record(1, false)}>Again</button><button disabled={!!feedback} onClick={() => record(2, true)}>Hard</button><button disabled={!!feedback} onClick={() => record(3, true)}>Good</button><button disabled={!!feedback} onClick={() => record(4, true)}>Easy</button></div></div>}</div>}
      {feedback && <div className={feedback.correct ? "feedback ok" : "feedback ng"}><b>{feedback.text}</b>{current.explanation && <p>{current.explanation}</p>}<button className="primary" onClick={next}>次へ</button></div>}
    </div>
  </div>;

  return <div className="panel study-setup"><div className="panel-title"><h3>出題する教材</h3><span>複数選択可</span></div>
    <div className="check-list">{materials.map(m => <label key={m.id}><input type="checkbox" checked={selected.includes(m.id)} onChange={e => setSelected(items => e.target.checked ? [...items, m.id] : items.filter(x => x !== m.id))} /><div><b>{m.name}</b><small>{m.question_count}問 / {m.due_count} due</small></div></label>)}</div>
    <label className="field small"><span>問題数</span><input type="number" min="1" max="100" value={limit} onChange={e => setLimit(Number(e.target.value))} /></label>
    <button className="primary" disabled={!selected.length || busy} onClick={start}>{busy ? "準備中…" : "セッション開始"}</button>
  </div>;
}

function Materials({ materials, refresh }: { materials: Material[]; refresh: () => void }) {
  const [selected, setSelected] = useState("");
  const [imports, setImports] = useState<ImportSource[]>([]);
  const [message, setMessage] = useState("");
  const selectedMaterial = materials.find(m => m.id === selected);
  const loadImports = async (id: string) => {
    setSelected(id); setImports(id ? await api<ImportSource[]>(`/materials/${id}/imports`) : []);
  };
  useEffect(() => {
    if (materials.length && !selected) loadImports(materials[0].id).catch(() => undefined);
  }, [materials]);

  const createMaterial = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const fd = new FormData(e.currentTarget);
    await api("/materials", { method: "POST", body: JSON.stringify({
      name: fd.get("name"), description: fd.get("description"), category: fd.get("category"),
      default_prompt_lang: fd.get("plang"), default_answer_lang: fd.get("alang")
    }) });
    e.currentTarget.reset(); refresh();
  };
  const editMaterial = async () => {
    if (!selectedMaterial) return;
    const name = prompt("教材名", selectedMaterial.name); if (name === null || !name.trim()) return;
    const description = prompt("説明", selectedMaterial.description) ?? selectedMaterial.description;
    await api(`/materials/${selectedMaterial.id}`, { method: "PATCH", body: JSON.stringify({ name: name.trim(), description }) });
    refresh();
  };
  const archiveMaterial = async () => {
    if (!selectedMaterial || !confirm(`「${selectedMaterial.name}」をアーカイブしますか？ 学習履歴は保持されます。`)) return;
    await api(`/materials/${selectedMaterial.id}`, { method: "DELETE" }); setSelected(""); setImports([]); refresh();
  };
  const editImport = async (item: ImportSource) => {
    const name = prompt("取込元名", item.name); if (name === null || !name.trim()) return;
    const url = prompt("URL", item.url); if (url === null || !url.trim()) return;
    await api(`/imports/${item.id}`, { method: "PATCH", body: JSON.stringify({ name: name.trim(), url: url.trim() }) });
    await loadImports(selected);
  };
  const createImport = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault(); if (!selected) return; const fd = new FormData(e.currentTarget); setMessage("同期中…");
    try {
      await api(`/materials/${selected}/imports`, { method: "POST", body: JSON.stringify({ name: fd.get("name"), kind: fd.get("kind"), url: fd.get("url"), sync_now: true }) });
      setMessage("同期しました"); await loadImports(selected); refresh();
    } catch (err) { setMessage(String((err as Error).message)); }
  };

  return <div className="two-col">
    <div className="panel"><div className="panel-title"><h3>教材</h3><span>Material</span></div>
      <p className="muted">教材は学習上のまとまりです。Google Sheetsなどの取込元とは分離して管理します。</p>
      <div className="list">{materials.map(m => <button className={selected === m.id ? "list-row selected" : "list-row"} onClick={() => loadImports(m.id)} key={m.id}><div><b>{m.name}</b><small>{m.category} · {m.question_count}問</small></div><span>{m.due_count}</span></button>)}</div>
      {selectedMaterial && <div className="row-actions material-actions"><button onClick={editMaterial}>教材を編集</button><button className="danger" onClick={archiveMaterial}>アーカイブ</button></div>}
      <form className="form" onSubmit={createMaterial}><h4>教材を追加</h4><input required name="name" placeholder="教材名" /><textarea name="description" placeholder="説明" /><div className="form-grid"><input name="category" placeholder="category" defaultValue="general" /><input name="plang" placeholder="問題言語 例: ru" /><input name="alang" placeholder="解答言語 例: ja" /></div><button className="primary">追加</button></form>
    </div>
    <div className="panel"><div className="panel-title"><h3>取込元</h3><span>Import source</span></div>
      <p className="muted">取込元を削除しても、取り込んだ問題は手動問題として残り、レビュー履歴も保持されます。</p>
      {!selected ? <p className="muted">教材を選択してください。</p> : <><div className="list">{imports.map(item => <div className="import-row" key={item.id}><div><b>{item.name}</b><small>{item.kind} · {item.last_sync_status}</small><code>{item.url}</code>{item.last_sync_error && <em>{item.last_sync_error}</em>}</div><div className="row-actions"><button onClick={() => editImport(item)}>編集</button><button onClick={async () => { await api(`/imports/${item.id}/sync`, { method: "POST" }); await loadImports(selected); refresh(); }}>同期</button><button className="danger" onClick={async () => { if (confirm("取込元を削除しますか？ 既存問題と履歴は保持されます。")) { await api(`/imports/${item.id}`, { method: "DELETE" }); await loadImports(selected); } }}>削除</button></div></div>)}</div>
      <form className="form" onSubmit={createImport}><h4>取込元を追加</h4><input required name="name" placeholder="名前" defaultValue="Google Sheets" /><select name="kind"><option value="google_sheets">Google Sheets</option><option value="csv_url">CSV URL</option></select><input required name="url" placeholder="https://docs.google.com/spreadsheets/d/..." /><button className="primary">登録して同期</button>{message && <small>{message}</small>}</form></>}
    </div>
  </div>;
}

function Questions({ materials, refresh }: { materials: Material[]; refresh: () => void }) {
  const [items, setItems] = useState<Question[]>([]);
  const [query, setQuery] = useState("");
  const [material, setMaterial] = useState("");
  const [edit, setEdit] = useState<Question | null>(null);
  const load = async () => setItems(await api<Question[]>(`/questions?limit=300${query ? `&q=${encodeURIComponent(query)}` : ""}${material ? `&material_ids=${material}` : ""}`));
  useEffect(() => { load().catch(() => undefined); }, [material]);

  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const fd = new FormData(e.currentTarget);
    const body = {
      material_id: fd.get("material_id"), prompt: fd.get("prompt"), answer: fd.get("answer"),
      explanation: fd.get("explanation"), question_type: fd.get("question_type"),
      prompt_lang: fd.get("prompt_lang"), answer_lang: fd.get("answer_lang"),
      choices: String(fd.get("choices") || "").split("|").map(x => x.trim()).filter(Boolean),
      tags: String(fd.get("tags") || "").split(/[|,;]/).map(x => x.trim()).filter(Boolean)
    };
    if (edit) await api(`/questions/${edit.id}`, { method: "PATCH", body: JSON.stringify(body) });
    else await api("/questions", { method: "POST", body: JSON.stringify(body) });
    setEdit(null); e.currentTarget.reset(); await load(); refresh();
  };

  return <div className="two-col questions-layout"><div className="panel"><div className="toolbar"><input value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === "Enter" && load()} placeholder="問題・答え・解説を検索" /><select value={material} onChange={e => setMaterial(e.target.value)}><option value="">全教材</option>{materials.map(m => <option value={m.id} key={m.id}>{m.name}</option>)}</select><button onClick={load}>検索</button></div><div className="question-list">{items.map(q => <div className="question-row" key={q.id}><div><div className="tagline">{q.tags.map(t => <span key={t}>{t}</span>)}</div><b>{q.prompt}</b><p>{q.answer}</p></div><div className="row-actions"><button onClick={() => setEdit(q)}>編集</button><button className="danger" onClick={async () => { if (confirm("この問題をアーカイブしますか？ 学習履歴は保持されます。")) { await api(`/questions/${q.id}`, { method: "DELETE" }); await load(); refresh(); } }}>削除</button></div></div>)}</div></div>
    <div className="panel sticky"><form key={edit?.id || "new"} className="form" onSubmit={save}><div className="panel-title"><h3>{edit ? "問題を編集" : "問題を追加"}</h3>{edit && <button type="button" className="ghost" onClick={() => setEdit(null)}>新規に戻す</button>}</div><select required name="material_id" defaultValue={edit?.material_id || materials[0]?.id} disabled={!!edit}>{materials.map(m => <option value={m.id} key={m.id}>{m.name}</option>)}</select><textarea required name="prompt" placeholder="問題" defaultValue={edit?.prompt} /><textarea required name="answer" placeholder="正答" defaultValue={edit?.answer} /><textarea name="explanation" placeholder="解説" defaultValue={edit?.explanation} /><input name="choices" placeholder="選択肢を | 区切り（省略可）" defaultValue={edit?.choices.join("|")} /><input name="tags" placeholder="タグを , 区切り" defaultValue={edit?.tags.join(",")} /><div className="form-grid"><select name="question_type" defaultValue={edit?.question_type || "auto"}><option value="auto">auto</option><option value="multiple_choice">multiple choice</option><option value="card">card</option></select><input name="prompt_lang" placeholder="prompt lang" defaultValue={edit?.prompt_lang} /><input name="answer_lang" placeholder="answer lang" defaultValue={edit?.answer_lang} /></div><button className="primary">{edit ? "保存" : "追加"}</button></form></div></div>;
}

function McpSettings() {
  const [value, setValue] = useState(token());
  const endpoint = `${location.origin}/mcp/`;
  const tools = ["list_materials", "search_questions", "create_study_session", "submit_review", "create_question", "sync_import", "get_learning_stats"];
  return <div className="stack"><div className="panel"><div className="panel-title"><h3>MCP endpoint</h3><span>Streamable HTTP</span></div><div className="endpoint"><code>{endpoint}</code><button onClick={() => navigator.clipboard.writeText(endpoint)}>コピー</button></div><p className="muted">MCPサーバは同じASGIアプリにマウントされ、RESTと同じサービス層・PostgreSQL・SRSを使用します。</p><div className="tool-grid">{tools.map(t => <code key={t}>{t}</code>)}</div></div>
    <div className="panel"><div className="panel-title"><h3>API token</h3><span>optional</span></div><p className="muted">サーバ側で PONKAN_API_TOKEN を設定した場合のみ必要です。この値はこのブラウザのlocalStorageだけに保存されます。</p><div className="endpoint"><input type="password" value={value} onChange={e => setValue(e.target.value)} placeholder="Bearer token" /><button onClick={() => { localStorage.setItem("ponkan.apiToken", value); location.reload(); }}>保存</button></div></div>
    <div className="panel"><h3>外部公開について</h3><p>そのままインターネットへ公開せず、Tailscale / WireGuard または認証付きリバースプロキシの利用を推奨します。MCPではDNS rebinding対策のため、実際に使うホスト名/IPを <code>PONKAN_MCP_ALLOWED_HOSTS</code> に明示してください。</p></div></div>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
