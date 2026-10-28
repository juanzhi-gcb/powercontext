import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowRight, ArrowUpRight, BookOpen, Check, ChevronRight, FileText, Info, LibraryBig, LoaderCircle, LockKeyhole, NotebookPen, RotateCcw, ScrollText, ShieldCheck, X } from "lucide-react";
import archivist from "../assets/archivist.png";
import { api, staticDemo } from "../api";
import { searchPublicArchive } from "../publicEngine";
import { sampleSecretary } from "../sample";
import type { HistorySearchResponse, Page, SecretaryReport, SourceRecord } from "../types";
import { DecisionBadge } from "./DecisionBadge";
import { HallArchivesSheet, type HallSheetKind } from "./HallArchives";

const COIN_KEY = "nullpath.coins.v1";
const STARTER_COINS = 20;
const ranks = [
  { min: 0, name: "见习馆员" },
  { min: 50, name: "夜班馆员" },
  { min: 120, name: "考据员" },
  { min: 240, name: "首席考据官" },
];
const stanceLabels = { supports: "支持", refutes: "反证", limits: "限制" };
const demoSources = [
  { title: "Attention Is All You Need", date: "2017-06-12" },
  { title: "BERT: Pre-training of Deep Bidirectional Transformers", date: "2018-10-11" },
  { title: "复现记录：小规模注意力消融", date: "2026-09-30" },
];

function readCoins() {
  try {
    const raw = window.localStorage.getItem(COIN_KEY);
    return raw ? Number(raw) || STARTER_COINS : STARTER_COINS;
  } catch {
    return STARTER_COINS;
  }
}

function HallMark() {
  return <svg viewBox="0 0 38 38" aria-hidden="true"><path d="M5 30V8l14 14L33 8v22" /><path d="M5 30h28" /><circle cx="19" cy="22" r="3" /></svg>;
}

function SceneBackdrop() {
  const folders = (x: number, y: number, widths: number[]) => widths.map((w, index) => (
    <rect key={`${x}-${y}-${index}`} x={x + index * (w + 4)} y={y} width={w} height="46" rx="2" fill={["#6b5a3c", "#7c6743", "#5c4d33", "#8a744c"][index % 4]} opacity=".75" />
  ));
  return <div className="hall-backdrop" aria-hidden="true">
    <div className="hall-lamp-glow" />
    <svg className="hall-shelves" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id="hallWood" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#4a3423" />
          <stop offset="1" stopColor="#2a1d14" />
        </linearGradient>
        <radialGradient id="hallLamp">
          <stop offset="0" stopColor="#ffcf82" stopOpacity=".55" />
          <stop offset="1" stopColor="#ffcf82" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="hallWall" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0d1a17" />
          <stop offset=".55" stopColor="#13231d" />
          <stop offset="1" stopColor="#1b2a21" />
        </linearGradient>
      </defs>
      <rect width="1600" height="900" fill="url(#hallWall)" />
      <g opacity=".5" stroke="#2c4034" strokeWidth="2">
        <path d="M0 210 H470 M0 360 H470 M0 510 H470 M1130 210 H1600 M1130 360 H1600 M1130 510 H1600" />
      </g>
      <g opacity=".55">
        {folders(40, 164, [34, 26, 40, 30, 36, 24])}
        {folders(300, 164, [28, 36, 24, 40])}
        {folders(58, 314, [40, 30, 26, 34, 38])}
        {folders(320, 314, [26, 38, 32, 24])}
        {folders(46, 464, [30, 24, 38, 28, 34, 26])}
        {folders(304, 464, [38, 26, 32])}
        {folders(1180, 164, [34, 28, 40, 30, 26])}
        {folders(1420, 164, [30, 36, 24])}
        {folders(1196, 314, [28, 36, 26, 38, 30])}
        {folders(1440, 314, [34, 24])}
        {folders(1174, 464, [38, 26, 30, 24])}
        {folders(1418, 464, [28, 34, 26])}
      </g>
      <g opacity=".4" fill="#20332a">
        <rect x="488" y="150" width="150" height="210" rx="6" />
        <rect x="962" y="150" width="150" height="210" rx="6" />
      </g>
      <g opacity=".5" stroke="#445a48" strokeWidth="1.5">
        {Array.from({ length: 12 }, (_, row) => Array.from({ length: 3 }, (_, col) => (
          <rect key={`drawer-${row}-${col}`} x={500 + col * 44} y={166 + row * 15} width="38" height="11" rx="2" fill="#2b3d31" />
        )))}
      </g>
      <g opacity=".35">
        <rect x="930" y="182" width="214" height="168" rx="8" fill="#172720" stroke="#3d5344" />
        <rect x="946" y="200" width="182" height="18" rx="4" fill="#3d5344" />
        <rect x="946" y="228" width="182" height="18" rx="4" fill="#3d5344" />
        <rect x="946" y="256" width="182" height="18" rx="4" fill="#3d5344" />
        <rect x="946" y="284" width="182" height="18" rx="4" fill="#3d5344" />
      </g>
      <g opacity=".7">
        <line x1="800" y1="0" x2="800" y2="76" stroke="#1d1a13" strokeWidth="4" />
        <path d="M742 128 Q800 64 858 128 Z" fill="#3a3021" />
        <ellipse cx="800" cy="128" rx="54" ry="8" fill="#c99632" opacity=".8" />
        <circle cx="800" cy="136" r="16" fill="url(#hallLamp)" />
        <circle cx="800" cy="136" r="26" fill="url(#hallLamp)" />
      </g>
      <g opacity=".55">
        <rect x="500" y="560" width="600" height="12" rx="3" fill="#3f2c1d" />
        <rect x="520" y="520" width="26" height="40" rx="2" fill="#6f5a3a" />
        <rect x="552" y="528" width="34" height="32" rx="2" fill="#58482f" />
        <rect x="1030" y="512" width="40" height="48" rx="2" fill="#6f5a3a" />
        <rect x="1078" y="524" width="30" height="36" rx="2" fill="#58482f" />
      </g>
    </svg>
    <div className="hall-vignette" />
  </div>;
}

function clipMechanism(text: string): string {
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > 260 ? `${compact.slice(0, 260).trimEnd()}…` : compact;
}

function Receipt({ result, demo, onClose, onContinue }: { result: HistorySearchResponse; demo: boolean; onClose: () => void; onContinue: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const evidenceCount = result.results.reduce((total, item) => total + item.evidence.length, 0);
  const stamp = result.results.length === 0 ? "查无旧档" : evidenceCount > 0 ? "有出处" : "待补出处";
  const serial = `${new Date().toISOString().slice(0, 10).replaceAll("-", "")}-${String(result.results.length).padStart(2, "0")}`;

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return <div className="hall-receipt-wrap">
    <article className="hall-receipt" aria-label="检索回执">
      <button ref={closeRef} className="hall-receipt-close" onClick={onClose} aria-label="收回回执"><X size={17} /></button>
      <header className="hall-receipt-head">
        <div><span>{demo ? "PUBLIC ARCHIVE RECEIPT · 浏览器实时检索" : "SEEKDB RECEIPT · 真实查证"}</span><strong>检索回执</strong></div>
        <em>NO. {serial}</em>
      </header>
      <p className="hall-receipt-query">“{result.query}”</p>
      {demo && <p className="hall-receipt-demo"><Info size={13} />公开版在你的浏览器里检索公开馆藏；资料导入、人工终审与本地记忆需启动 seekdb。</p>}
      <div className="hall-receipt-summary">
        <div><strong>{result.results.length ? `翻到 ${result.results.length} 份旧档` : "档案里没有对得上的记录"}</strong><span>{result.results.length ? `其中 ${evidenceCount} 条可定位证据；没找到也不等于创新成立。` : "可以补一句机制描述，或把资料先收进馆藏再查。"}</span></div>
        <div className="hall-stamp">{stamp}</div>
      </div>
      {result.results.length > 0 && <ol className="hall-receipt-list">
        {result.results.map((item, index) => <li key={item.attempt_id}>
          <div className="hall-receipt-row">
            <span className="hall-receipt-index">{String(index + 1).padStart(2, "0")}</span>
            <div>
              <div className="hall-receipt-title"><h3>{item.title}</h3>{item.historical_decision && <DecisionBadge decision={item.historical_decision} />}</div>
              <div className="hall-receipt-meta">{item.task} · {item.evidence.length} 条可定位证据{item.available_at ? ` · ${item.available_at.slice(0, 10)}` : ""}</div>
              <p className="hall-receipt-mechanism">{clipMechanism(item.mechanism)}</p>
              {item.evidence.map((evidence) => <details className="hall-receipt-evidence" key={evidence.id}>
                <summary><FileText size={13} />{evidence.title}<span className={`stance stance-${evidence.stance}`}>{stanceLabels[evidence.stance]}</span><ChevronRight size={13} /></summary>
                <blockquote>{evidence.excerpt}</blockquote>
                {/^https?:\/\//.test(evidence.locator) ? <a href={evidence.locator} target="_blank" rel="noreferrer">{evidence.locator}<ArrowUpRight size={12} /></a> : <code>{evidence.locator}</code>}
              </details>)}
            </div>
          </div>
        </li>)}
      </ol>}
      <footer className="hall-receipt-foot">
        <p><ShieldCheck size={14} />回执只说明查到什么，不替你做决定。</p>
        <div>
          <button className="hall-paper-btn" onClick={onClose}>再递一张</button>
          {result.results.length > 0 && <button className="hall-brass-btn" onClick={onContinue}>继续正式考据<ArrowRight size={15} /></button>}
        </div>
      </footer>
    </article>
  </div>;
}

export function ArchiveHall({ live, onContinue, onNavigate }: { live: boolean; onContinue: (idea: string) => void; onNavigate: (page: Page) => void }) {
  const demo = staticDemo;
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<HistorySearchResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [coins, setCoins] = useState(readCoins);
  const [coinGain, setCoinGain] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [sources, setSources] = useState<SourceRecord[]>([]);
  const [secretary, setSecretary] = useState<SecretaryReport | null>(null);
  const [sheet, setSheet] = useState<HallSheetKind | null>(null);
  const [sheetSeed, setSheetSeed] = useState("");
  const [sheetKey, setSheetKey] = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (demo || !live) return;
    api.listSources().then(setSources).catch(() => undefined);
    api.getSecretary().then(setSecretary).catch(() => undefined);
  }, [demo, live]);

  const rank = [...ranks].reverse().find((item) => coins >= item.min) ?? ranks[0];
  const nextRank = ranks.find((item) => item.min > coins);
  const progress = nextRank ? Math.min(1, (coins - rank.min) / (nextRank.min - rank.min)) : 1;
  const pendingCount = demo ? sampleSecretary.proposals.filter((item) => item.status === "proposed").length : secretary?.proposals.filter((item) => item.status === "proposed").length ?? 0;
  const sourceCount = demo ? sampleSecretary.source_count : sources.length;
  const acceptedCount = demo ? sampleSecretary.accepted_count : secretary?.accepted_count ?? 0;
  const recent = demo ? demoSources : sources.slice(0, 3).map((item) => ({ title: item.title, date: item.available_at.slice(0, 10) }));

  function award(amount: number, reason: string) {
    setCoins((current) => {
      const next = current + amount;
      try { window.localStorage.setItem(COIN_KEY, String(next)); } catch { /* storage may be unavailable */ }
      return next;
    });
    setCoinGain(`+${amount} 考据币 · ${reason}`);
    window.setTimeout(() => setCoinGain(""), 2600);
  }

  async function runSearch(text: string) {
    setQuery(text);
    setPending(true);
    setError("");
    try {
      const next = demo ? await searchPublicArchive(text) : await api.searchHistory(text);
      setResult(next);
      const hasEvidence = next.results.some((item) => item.evidence.length > 0);
      award(hasEvidence ? 15 : 10, hasEvidence ? "查到可定位出处" : "完成一次查证");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "检索失败，馆员暂时翻不到档案。");
    } finally {
      setPending(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = (inputRef.current?.value ?? query).trim();
    if (!text) {
      setError("先写一句想查的想法，老余才翻得动旧档。");
      inputRef.current?.focus();
      return;
    }
    await runSearch(text);
  }

  function openSheet(kind: HallSheetKind, seed = "") {
    setMenuOpen(false);
    setSheetSeed(seed);
    setSheetKey((current) => current + 1);
    setSheet(kind);
  }

  function go(page: Page) {
    if (!demo) {
      onNavigate(page);
      return;
    }
    if (page === "sources") openSheet("library");
    else if (page === "secretary") openSheet("secretary");
    else if (page === "report" || page === "evidence" || page === "regression") openSheet("verdicts");
    else if (page === "project" || page === "context") openSheet("project");
    else if (page === "new") openSheet("precheck");
  }

  function returnToDesk() {
    setSheet(null);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }

  function searchFromSheet(text?: string) {
    setSheet(null);
    if (text) {
      void runSearch(text);
      return;
    }
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }

  function onNoteKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  const menuGroups: { label: string; items: { id: Page; label: string; detail: string; icon: typeof LibraryBig }[] }[] = demo ? [
    { label: "开始使用", items: [
      { id: "sources", label: "我的馆藏", detail: "3 份随构建打包的公开资料", icon: LibraryBig },
      { id: "new", label: "正式考据", detail: "在浏览器里完成一次确定性预检", icon: ScrollText },
    ] },
    { label: "高级功能", items: [
      { id: "secretary", label: "研究秘书", detail: "知识线提案，只提案不拍板", icon: NotebookPen },
      { id: "report", label: "取回旧裁决", detail: "NO_GO / CONDITIONAL_GO 与原始出处", icon: BookOpen },
    ] },
    { label: "交付", items: [
      { id: "project", label: "技术档案", detail: "技术分工、复现方式与仓库", icon: BookOpen },
    ] },
  ] : [
    { label: "开始使用", items: [
      { id: "sources", label: "我的馆藏", detail: "导入并查看自己的论文与记录", icon: LibraryBig },
      { id: "new", label: "正式考据", detail: "完成确定性预检与最小实验条件", icon: ScrollText },
    ] },
    { label: "高级功能", items: [
      { id: "secretary", label: "研究秘书", detail: "知识线提案与人工审阅", icon: NotebookPen },
      { id: "report", label: "预检报告", detail: "查看机器建议与检查依据", icon: BookOpen },
      { id: "evidence", label: "证据出处", detail: "从裁决回到原文与稳定定位", icon: FileText },
      { id: "regression", label: "历史回放", detail: "按历史时点重放一次判断", icon: RotateCcw },
      { id: "context", label: "记忆与状态", detail: "PowerContext 工作状态", icon: Check },
    ] },
    { label: "交付", items: [
      { id: "project", label: "技术档案", detail: "运行方式、验证证据与仓库", icon: BookOpen },
    ] },
  ];

  return <div className="hall">
    <SceneBackdrop />
    <div className="hall-hero-glow" aria-hidden="true" />
    <img className="hall-hero" src={archivist} alt="夜班馆员老余" />
    <div className="hall-counter" aria-hidden="true" />
    <header className="hall-top">
      <div className="hall-brand">
        <HallMark />
        <div><strong>NullPath</strong><small>研究档案馆</small></div>
      </div>
      <div className="hall-top-right">
        <span className={`hall-status ${live ? "is-live" : "is-demo"}`}><i />{live ? "灯亮着 · 服务在线" : demo ? "公开馆藏 · 实时检索" : "本地服务未连接"}</span>
        <div className="hall-coins" title="只奖励查证动作，不奖励结论">
          <span className="hall-coin">考</span>
          <strong>{coins}</strong>
          <em>{rank.name}{nextRank ? ` · 距${nextRank.name} ${nextRank.min - coins}` : ""}</em>
          {coinGain && <span className="hall-coin-gain">{coinGain}</span>}
        </div>
        <button className="hall-menu-button" onClick={() => setMenuOpen(true)}>档案柜<ChevronRight size={15} /></button>
      </div>
    </header>

    <div className="hall-sign">
      <span>NULLPATH ARCHIVE · 深夜值班</span>
      <h1>研究档案馆</h1>
      <p>给研究想法查一次旧账 · 只收证据，不收故事</p>
    </div>

    <aside className="hall-panel hall-panel-left">
      <header><span>今日归档</span><em>只收证据</em></header>
      <ul>
        {recent.length > 0 ? recent.map((item) => <li key={item.title}>
          <button onClick={() => go("sources")}>
            <span className="hall-file-icon"><FileText size={14} /></span>
            <span><strong>{item.title}</strong><small>{item.date || "日期待补"}</small></span>
            <em>已收</em>
          </button>
        </li>) : <li className="hall-panel-empty">馆藏还是空的。先收一份自己的论文或复现记录。</li>}
      </ul>
      <footer><button onClick={() => go("sources")}><LibraryBig size={14} />馆藏 {sourceCount} 份 · {demo ? "查看" : "去整理"}<ArrowRight size={13} /></button></footer>
    </aside>

    <aside className="hall-panel hall-panel-right">
      <header><span>值班台</span><em>{live ? "LIVE" : "PUBLIC"}</em></header>
      <div className="hall-ledger">
        <div><strong>{sourceCount}</strong><span>份资料入馆</span></div>
        <div><strong>{acceptedCount}</strong><span>条知识线</span></div>
        <div><strong>{pendingCount}</strong><span>条提案待核</span></div>
      </div>
      <button className="hall-ledger-link" onClick={() => go("secretary")}><NotebookPen size={14} />看看秘书提了什么<ChevronRight size={13} /></button>
      {pendingCount > 0 && <p className="hall-pending"><span />有 {pendingCount} 条提案等你拍板，馆员不替你决定。</p>}
      <div className="hall-rank">
        <div><span>馆员等级</span><em>{coins} / {nextRank ? nextRank.min : coins} 考据币</em></div>
        <div className="hall-rank-bar"><i style={{ width: `${Math.max(6, progress * 100)}%` }} /></div>
        <small>查证 +10，有出处再 +5；不奖励结论。</small>
      </div>
    </aside>

    <div className={`hall-speech ${pending ? "is-thinking" : ""}`}>
      {pending ? <><LoaderCircle className="spin" size={15} />老余在灯下翻档，别催……</> : result ? <><Check size={15} />回执出来了，先看出处。</> : <><LockKeyhole size={15} />把想法写在纸上，老余替你翻旧账。</>}
    </div>

    <div className="hall-desk">
      {error && <div className="hall-error" id="hall-error" role="alert">{error}</div>}
      <form className={`hall-note ${error ? "is-invalid" : ""}`} onSubmit={submit}>
        <div className="hall-note-field">
          <div className="hall-note-meta">
            <label htmlFor="hall-query">写在纸条上，推给馆员</label>
            <span className="hall-note-count">{query.trim().length === 0 ? "写得越具体，越容易翻到旧档" : `${query.trim().length} 字`}</span>
          </div>
          <textarea ref={inputRef} id="hall-query" rows={2} value={query} aria-invalid={Boolean(error)} aria-describedby={error ? "hall-error" : undefined} onChange={(event) => { setQuery(event.target.value); if (error) setError(""); }} onKeyDown={onNoteKeyDown} placeholder="例如：我想用自注意力替代循环结构，验证长距离依赖是否真的更好……" />
        </div>
        <button className="hall-push" type="submit" disabled={(!demo && !live) || pending}>
          {pending ? <LoaderCircle className="spin" size={17} /> : <ArrowRight size={17} />}{pending ? "查档中" : "推过去"}
        </button>
      </form>
      {!demo && !live && <div className="hall-error">本地服务未连接：现在只能看演示馆藏，启动 Compose 后可查自己的资料。</div>}
      <nav className="hall-actions" aria-label="档案馆快捷操作">
        <button onClick={() => inputRef.current?.focus()}><ScrollText size={14} />查一件想法</button>
        <button onClick={() => go("sources")}><LibraryBig size={14} />我的馆藏</button>
        <button onClick={() => go("report")}><FileText size={14} />取回旧裁决</button>
        <button onClick={() => go("project")}><BookOpen size={14} />技术档案</button>
        <span>Enter 递出 · Shift + Enter 换行</span>
      </nav>
    </div>

    {result && <Receipt result={result} demo={demo} onClose={() => { setResult(null); inputRef.current?.focus(); }} onContinue={() => {
      if (!demo) {
        onContinue(result.query);
        return;
      }
      setResult(null);
      openSheet("precheck", result.query);
    }} />}

    {sheet && <HallArchivesSheet key={sheetKey} kind={sheet} seed={sheetSeed} onClose={returnToDesk} onOpen={(kind) => openSheet(kind)} onSearch={() => searchFromSheet()} onSearchWith={searchFromSheet} />}

    {menuOpen && <div className="hall-drawer-backdrop" onClick={() => setMenuOpen(false)}>
      <aside className="hall-drawer" onClick={(event) => event.stopPropagation()} aria-label="档案柜导航">
        <header><div><span>ARCHIVE DRAWER</span><strong>档案柜</strong></div><button onClick={() => setMenuOpen(false)} aria-label="关闭档案柜"><X size={18} /></button></header>
        {menuGroups.map((group) => <section key={group.label}>
          <span className="hall-drawer-label">{group.label}</span>
          {group.items.map((item) => <button key={item.id} onClick={() => { setMenuOpen(false); go(item.id); }}>
            <item.icon size={17} />
            <span><strong>{item.label}</strong><small>{item.detail}</small></span>
            <ChevronRight size={14} />
          </button>)}
        </section>)}
        <footer>
          <span className={`hall-status ${live ? "is-live" : "is-demo"}`}><i />{live ? "seekdb · PowerContext 在线" : demo ? "公开馆藏 · 浏览器实时检索" : "本地服务未连接"}</span>
          <a href="https://github.com/AtoFuture/NullPath-Research-CI" target="_blank" rel="noreferrer">代码仓库<ArrowUpRight size={13} /></a>
        </footer>
      </aside>
    </div>}
  </div>;
}
