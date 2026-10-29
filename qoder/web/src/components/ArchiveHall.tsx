import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowRight, ArrowUpRight, BookMarked, BookOpen, Check, ChevronRight, Crown, Eye, FileText, Fingerprint, Lamp, LibraryBig, LoaderCircle, Medal, NotebookPen, RotateCcw, Ruler, ScrollText, Stamp, X } from "lucide-react";
import { api, staticDemo } from "../api";
import { listPublicVerdicts, publicArchiveStats, searchPublicArchive } from "../publicEngine";
import type { HistorySearchResponse, Page, SecretaryReport, SourceRecord } from "../types";
import { Archivist, type ArchivistMood } from "./Archivist";
import { DecisionBadge } from "./DecisionBadge";
import { HallArchivesSheet, type HallSheetKind } from "./HallArchives";
import { SourceTag, sourceMetaLead } from "./SourceTag";

const COIN_KEY = "nullpath.coins.v1";
const BADGE_KEY = "nullpath.badges.v1";
const STARTER_COINS = 20;
const badges = [
  { id: "night-lamp", name: "夜灯初证", price: 15, Icon: Lamp, detail: "袖口带灯油味，是夜班馆员的第一枚印章。" },
  { id: "old-eye", name: "旧档耳目", price: 30, Icon: Eye, detail: "别人先看结论，你先找出处。" },
  { id: "receipt-stamp", name: "回执验章", price: 45, Icon: Stamp, detail: "盖章之前，先核对证据落在哪一行。" },
  { id: "cold-case", name: "冷案猎手", price: 60, Icon: Fingerprint, detail: "专翻没人愿意重开的旧案。" },
  { id: "measure", name: "卡尺与墨", price: 80, Icon: Ruler, detail: "机制、差异、停止条件，一样都不许含糊。" },
  { id: "chief", name: "首席考据官", price: 120, Icon: Crown, detail: "馆里最高的座位，也只对证据负责。" },
];
type Badge = (typeof badges)[number];
type BadgeShelf = { owned: string[]; equipped: string | null };
const stanceLabels = { supports: "支持", refutes: "反证", limits: "限制" };
const archiveStats = publicArchiveStats();
const archiveVerdicts = listPublicVerdicts();

function readCoins() {
  try {
    const raw = window.localStorage.getItem(COIN_KEY);
    return raw ? Number(raw) || STARTER_COINS : STARTER_COINS;
  } catch {
    return STARTER_COINS;
  }
}

function readBadges(): BadgeShelf {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(BADGE_KEY) ?? "{}") as { owned?: unknown; equipped?: unknown };
    const known = new Set(badges.map((item) => item.id));
    const owned = Array.isArray(parsed.owned)
      ? [...new Set(parsed.owned.filter((id): id is string => typeof id === "string" && known.has(id)))]
      : [];
    const equipped = typeof parsed.equipped === "string" && owned.includes(parsed.equipped) ? parsed.equipped : null;
    return { owned, equipped };
  } catch {
    return { owned: [], equipped: null };
  }
}

function saveCoins(next: number) {
  try { window.localStorage.setItem(COIN_KEY, String(next)); } catch { /* storage may be unavailable */ }
}

function saveBadges(shelf: BadgeShelf) {
  try { window.localStorage.setItem(BADGE_KEY, JSON.stringify(shelf)); } catch { /* storage may be unavailable */ }
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

function Receipt({ result, demo, onClose, onAgain, onContinue }: { result: HistorySearchResponse; demo: boolean; onClose: () => void; onAgain: () => void; onContinue: () => void }) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const evidenceCount = result.results.reduce((total, item) => total + item.evidence.length, 0);
  const stamp = result.results.length === 0 ? "查无旧档" : evidenceCount > 0 ? "有出处" : "待补出处";
  const serial = `${new Date().toISOString().slice(0, 10).replaceAll("-", "")}-${String(result.results.length).padStart(2, "0")}`;

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return <div className="hall-receipt-wrap">
    <article className="hall-receipt" aria-label="检索回执">
      <button className="hall-receipt-close" onClick={onClose} aria-label="收回回执"><X size={17} /></button>
      <header className="hall-receipt-head">
        <div><span>{demo ? "PUBLIC ARCHIVE RECEIPT / 浏览器实时检索" : "SEEKDB RECEIPT / 真实查证"}</span><strong>检索回执</strong></div>
        <em>NO. {serial}</em>
      </header>
      <p className="hall-receipt-query">“{result.query}”</p>
      <div className="hall-receipt-summary">
        <div><strong>{result.results.length ? `翻到 ${result.results.length} 份旧档` : "档案里没有对得上的记录"}</strong><span>{result.results.length ? `其中 ${evidenceCount} 条可定位证据，点开可核对原文。` : "可以补一句机制描述，或把资料先收进馆藏再查。"}</span></div>
        <div className="hall-stamp">{stamp}</div>
      </div>
      {result.results.length > 0 && <ol className="hall-receipt-list">
        {result.results.map((item, index) => <li key={item.attempt_id}>
          <div className="hall-receipt-row">
            <span className="hall-receipt-index">{String(index + 1).padStart(2, "0")}</span>
            <div>
              <div className="hall-receipt-title"><h3>{item.title}</h3>{item.historical_decision && <DecisionBadge decision={item.historical_decision} />}</div>
              <div className="hall-receipt-meta"><SourceTag source={item.source} recordType={item.record_type} url={item.source_url} />{sourceMetaLead(item.source, item.record_type, item.outcome, item.task)}，{item.evidence.length} 条可定位证据{item.available_at ? `，${item.available_at.slice(0, 10)}` : ""}</div>
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
      <footer className="hall-receipt-foot is-actions">
        <div>
          <button className="hall-paper-btn" onClick={onAgain}>再递一张</button>
          {result.results.length > 0 && <button className="hall-brass-btn" onClick={onContinue}>继续正式考据<ArrowRight size={15} /></button>}
        </div>
      </footer>
    </article>
  </div>;
}

function HallGuide({ onClose }: { onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return <div className="hall-guide-backdrop" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="hall-guide-scroll" role="dialog" aria-modal="true" aria-labelledby="hall-guide-title">
      <span className="hall-guide-roll is-top" aria-hidden="true" />
      <article className="hall-guide">
        <button ref={closeRef} className="hall-guide-close" onClick={onClose} aria-label="收起档案馆入棺须知"><X size={16} /></button>
        <header>
          <span>NIGHT SHIFT NOTES / 老余手记</span>
          <h2 id="hall-guide-title">档案馆入棺须知</h2>
          <p>夜班馆员留给你的四张便签</p>
        </header>
        <ol className="hall-guide-steps">
          <li><span>壹</span><div><strong>写纸条</strong><p>把研究想法写在柜台上的纸条里。Enter 递出，Shift + Enter 换行。</p></div></li>
          <li><span>贰</span><div><strong>看回执</strong><p>回执只列翻到的旧档和可定位出处。点开证据核对原文，再决定要不要继续正式考据。</p></div></li>
          <li><span>叁</span><div><strong>正式考据</strong><p>从回执点「继续正式考据」，补齐机制、差异和停止条件，生成避坑报告。</p></div></li>
          <li><span>肆</span><div><strong>翻旧案</strong><p>「取回旧裁决」看以前为什么停；「技术档案」看技术分工和本地运行方式。</p></div></li>
        </ol>
        <footer>
          <span className="hall-guide-stamp">老余</span>
          <p>查证 +10，有出处再 +5。考据币可在徽章铺换章。</p>
        </footer>
      </article>
      <span className="hall-guide-roll is-bottom" aria-hidden="true" />
    </div>
  </div>;
}

function BadgeShop({ coins, shelf, onBuy, onEquip, onClose }: { coins: number; shelf: BadgeShelf; onBuy: (badge: Badge) => void; onEquip: (id: string | null) => void; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [note, setNote] = useState("");
  const owned = new Set(shelf.owned);
  const worn = badges.find((item) => item.id === shelf.equipped) ?? null;

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  function choose(item: Badge) {
    if (owned.has(item.id)) {
      const next = shelf.equipped === item.id ? null : item.id;
      onEquip(next);
      setNote(next ? `已佩戴「${item.name}」` : `已摘下「${item.name}」`);
      return;
    }
    if (coins < item.price) return;
    onBuy(item);
    setNote(`已购「${item.name}」，余 ${coins - item.price} 枚考据币`);
  }

  return <div className="hall-guide-backdrop" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="hall-guide-scroll hall-shop-scroll" role="dialog" aria-modal="true" aria-labelledby="hall-shop-title">
      <span className="hall-guide-roll is-top" aria-hidden="true" />
      <article className="hall-guide hall-shop">
        <button ref={closeRef} className="hall-guide-close" onClick={onClose} aria-label="收起徽章铺"><X size={16} /></button>
        <header>
          <span>NIGHT SHIFT BADGE SHOP / 老余的抽屉</span>
          <h2 id="hall-shop-title">考据徽章</h2>
        </header>
        <div className="hall-shop-balance">
          <span className="hall-coin">考</span>
          <strong>{coins}</strong>
          <em>枚可用</em>
          <span className="hall-shop-worn">{worn ? <>佩戴中：{worn.name}</> : "尚未佩戴徽章"}</span>
        </div>
        {note && <p className="hall-shop-note" role="status">{note}</p>}
        <div className="hall-shop-grid">
          {badges.map((item) => {
            const has = owned.has(item.id);
            const isWorn = shelf.equipped === item.id;
            const affordable = coins >= item.price;
            return <div key={item.id} className={`hall-shop-card ${has ? "is-owned" : ""} ${isWorn ? "is-worn" : ""}`}>
              <span className="hall-shop-emblem"><item.Icon size={21} strokeWidth={1.7} /></span>
              <div className="hall-shop-copy">
                <strong>{item.name}</strong>
                <p>{item.detail}</p>
                <span className="hall-shop-price">{has ? "已入册" : `${item.price} 考据币`}</span>
              </div>
              <button type="button" className={isWorn ? "is-worn" : ""} disabled={!has && !affordable} onClick={() => choose(item)}>
                {isWorn ? "摘下" : has ? "佩戴" : affordable ? "购下" : `还差 ${item.price - coins}`}
              </button>
            </div>;
          })}
        </div>
        <footer className="hall-shop-foot">
          <span className="hall-guide-stamp">老余</span>
          <p>换章不退币，摘下不扣币。</p>
        </footer>
      </article>
      <span className="hall-guide-roll is-bottom" aria-hidden="true" />
    </div>
  </div>;
}

export function ArchiveHall({ live, onContinue, onNavigate }: { live: boolean; onContinue: (idea: string) => void; onNavigate: (page: Page) => void }) {
  const demo = staticDemo;
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<HistorySearchResponse | null>(null);
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [coins, setCoins] = useState(readCoins);
  const [coinGain, setCoinGain] = useState("");
  const [shelf, setShelf] = useState(readBadges);
  const [shopOpen, setShopOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [sources, setSources] = useState<SourceRecord[]>([]);
  const [secretary, setSecretary] = useState<SecretaryReport | null>(null);
  const [sheet, setSheet] = useState<HallSheetKind | null>(null);
  const [sheetSeed, setSheetSeed] = useState("");
  const [sheetKey, setSheetKey] = useState(0);
  const [guideOpen, setGuideOpen] = useState(false);
  const [listening, setListening] = useState(false);
  const [cheer, setCheer] = useState<string | null>(null);
  const [recentBadge, setRecentBadge] = useState("");
  const cheerTimer = useRef<number | undefined>(undefined);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const searchSeq = useRef(0);

  useEffect(() => () => window.clearTimeout(cheerTimer.current), []);

  useEffect(() => {
    if (demo || !live) return;
    api.listSources().then(setSources).catch(() => undefined);
    api.getSecretary().then(setSecretary).catch(() => undefined);
  }, [demo, live]);

  const wornBadge = badges.find((item) => item.id === shelf.equipped) ?? null;
  const ownedCount = badges.filter((item) => shelf.owned.includes(item.id)).length;
  const pendingCount = secretary?.proposals.filter((item) => item.status === "proposed").length ?? 0;
  const sourceCount = sources.length;
  const acceptedCount = secretary?.accepted_count ?? 0;
  const recent = demo
    ? archiveVerdicts.slice(0, 3).map((item) => ({ title: item.title, date: item.available_at.slice(0, 10) }))
    : sources.slice(0, 3).map((item) => ({ title: item.title, date: item.available_at.slice(0, 10) }));
  const hasEvidence = result?.results.some((item) => item.evidence.length > 0) ?? false;
  const mood: ArchivistMood = pending
    ? "think"
    : error
      ? "error"
      : cheer
        ? "pleased"
        : result
          ? (hasEvidence ? "found" : "blank")
          : listening
            ? "listen"
            : "idle";

  function cheerWith(text: string) {
    window.clearTimeout(cheerTimer.current);
    setCheer(text);
    cheerTimer.current = window.setTimeout(() => setCheer(null), 4200);
  }

  function award(amount: number, reason: string) {
    setCoins((current) => {
      const next = current + amount;
      saveCoins(next);
      return next;
    });
    setCoinGain(`+${amount} 考据币，${reason}`);
    window.setTimeout(() => setCoinGain(""), 2600);
  }

  function buyBadge(badge: Badge) {
    if (shelf.owned.includes(badge.id) || coins < badge.price) return;
    const nextCoins = coins - badge.price;
    const nextShelf = { owned: [...shelf.owned, badge.id], equipped: badge.id };
    setCoins(nextCoins);
    saveCoins(nextCoins);
    setShelf(nextShelf);
    saveBadges(nextShelf);
    setRecentBadge(badge.name);
  }

  function closeShop() {
    setShopOpen(false);
    if (recentBadge) {
      cheerWith(`「${recentBadge}」别在衣襟上了。`);
      setRecentBadge("");
    }
  }

  function equipBadge(id: string | null) {
    const nextShelf = { ...shelf, equipped: id };
    setShelf(nextShelf);
    saveBadges(nextShelf);
  }

  async function runSearch(text: string) {
    const seq = ++searchSeq.current;
    setQuery(text);
    setPending(true);
    setError("");
    setResult(null);
    setReceiptOpen(false);
    setCheer(null);
    const startedAt = performance.now();
    try {
      const next = demo ? await searchPublicArchive(text) : await api.searchHistory(text);
      const remaining = 520 - (performance.now() - startedAt);
      if (remaining > 0) await new Promise((resolve) => window.setTimeout(resolve, remaining));
      if (seq !== searchSeq.current) return;
      setResult(next);
      setReceiptOpen(true);
      const hasEvidence = next.results.some((item) => item.evidence.length > 0);
      award(hasEvidence ? 15 : 10, hasEvidence ? "查到可定位出处" : "完成一次查证");
    } catch (reason) {
      if (seq !== searchSeq.current) return;
      setError(reason instanceof Error ? reason.message : "检索失败，馆员暂时翻不到档案。");
    } finally {
      if (seq === searchSeq.current) setPending(false);
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
    if (page === "report" || page === "evidence" || page === "regression" || page === "sources" || page === "secretary") openSheet("verdicts");
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

  const menuGroups: { label: string; items: { id: Page | "guide" | "badges"; label: string; detail?: string; icon: typeof LibraryBig }[] }[] = demo ? [
    { label: "开始使用", items: [
      { id: "new", label: "正式考据", icon: ScrollText },
      { id: "guide", label: "档案馆入棺须知", icon: BookMarked },
      { id: "badges", label: "徽章铺", detail: "用考据币换馆员徽章", icon: Medal },
    ] },
    { label: "高级功能", items: [
      { id: "report", label: "取回旧裁决", icon: BookOpen },
    ] },
    { label: "交付", items: [
      { id: "project", label: "技术档案", icon: BookOpen },
    ] },
  ] : [
    { label: "开始使用", items: [
      { id: "sources", label: "我的馆藏", detail: "导入并查看自己的论文与记录", icon: LibraryBig },
      { id: "new", label: "正式考据", detail: "完成确定性预检与最小实验条件", icon: ScrollText },
      { id: "guide", label: "档案馆入棺须知", detail: "大厅操作速查", icon: BookMarked },
      { id: "badges", label: "徽章铺", detail: "用考据币换馆员徽章", icon: Medal },
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
    <Archivist mood={mood} />
    <div className="hall-counter" aria-hidden="true" />
    <header className="hall-top">
      <div className="hall-brand">
        <HallMark />
        <div><strong>NullPath</strong><small>研究档案馆</small></div>
      </div>
      <div className="hall-top-right">
        <span className={`hall-status ${live ? "is-live" : "is-demo"}`}><i />{live ? "灯亮着，服务在线" : demo ? "公开馆藏，实时检索" : "本地服务未连接"}</span>
        <button type="button" className="hall-coins" onClick={() => setShopOpen(true)} title="只奖励查证动作；点开徽章铺换章" aria-label={`考据币 ${coins}，打开徽章铺`}>
          <span className="hall-coin">考</span>
          <strong>{coins}</strong>
          <Medal className="hall-coin-medal" size={12} aria-hidden="true" />
          <em>{wornBadge ? `佩戴 ${wornBadge.name}` : `徽章 ${ownedCount}/${badges.length}`}</em>
          {coinGain && <span className="hall-coin-gain">{coinGain}</span>}
        </button>
        <button className="hall-menu-button" onClick={() => setMenuOpen(true)}>档案柜<ChevronRight size={15} /></button>
      </div>
    </header>

    <div className="hall-sign">
      <span>NULLPATH ARCHIVE / 深夜值班</span>
      <h1>研究档案馆</h1>
      <p>给研究想法查一次旧账，只收证据，不收故事</p>
    </div>

    <button className="hall-notice" onClick={() => setGuideOpen(true)} aria-label="打开档案馆入棺须知">
      <BookMarked size={18} />
      <strong>档案馆入棺须知</strong>
      <ChevronRight size={15} />
    </button>

    <div className="hall-side-actions is-left" aria-label="馆内操作">
      <button onClick={() => inputRef.current?.focus()}><ScrollText size={15} />查一件想法</button>
      <button onClick={() => go("new")}><NotebookPen size={15} />正式考据</button>
    </div>
    <div className="hall-side-actions is-right" aria-label="档案与交付">
      {!demo && <button onClick={() => go("sources")}><LibraryBig size={15} />我的馆藏</button>}
      <button onClick={() => go("report")}><FileText size={15} />取回旧裁决</button>
      <button onClick={() => go("project")}><BookOpen size={15} />技术档案</button>
    </div>

    <aside className="hall-panel hall-panel-left">
      <header><span>{demo ? "馆藏旧案" : "今日归档"}</span><em>只收证据</em></header>
      <ul>
        {recent.length > 0 ? recent.map((item) => <li key={item.title}>
          <button onClick={() => go(demo ? "report" : "sources")}>
            <span className="hall-file-icon"><FileText size={14} /></span>
            <span><strong>{item.title}</strong><small>{item.date || "日期待补"}</small></span>
            <em>{demo ? "旧案" : "已收"}</em>
          </button>
        </li>) : <li className="hall-panel-empty">馆藏还是空的。先收一份自己的论文或复现记录。</li>}
      </ul>
      <footer><button onClick={() => go(demo ? "report" : "sources")}>{demo ? <BookOpen size={14} /> : <LibraryBig size={14} />}{demo ? `旧裁决 ${archiveStats.verdicts} 份，查看` : `馆藏 ${sourceCount} 份，去整理`}<ArrowRight size={13} /></button></footer>
    </aside>

    <aside className="hall-panel hall-panel-right">
      <header><span>值班台</span><em>{live ? "LIVE" : "PUBLIC"}</em></header>
      <div className="hall-ledger">
        {demo ? <>
          <div><strong>{archiveStats.records}</strong><span>份馆藏</span></div>
          <div><strong>{archiveStats.withEvidence}</strong><span>份带证据</span></div>
          <div><strong>{archiveStats.verdicts}</strong><span>条旧裁决</span></div>
        </> : <>
          <div><strong>{sourceCount}</strong><span>份资料入馆</span></div>
          <div><strong>{acceptedCount}</strong><span>条知识线</span></div>
          <div><strong>{pendingCount}</strong><span>条提案待核</span></div>
        </>}
      </div>
      {demo
        ? <button className="hall-ledger-link" onClick={() => setGuideOpen(true)}><BookMarked size={14} />档案馆入棺须知<ChevronRight size={13} /></button>
        : <button className="hall-ledger-link" onClick={() => go("secretary")}><NotebookPen size={14} />看看秘书提了什么<ChevronRight size={13} /></button>}
      {!demo && pendingCount > 0 && <p className="hall-pending"><span />有 {pendingCount} 条提案等你拍板，馆员不替你决定。</p>}
      <button type="button" className="hall-badges" onClick={() => setShopOpen(true)} aria-label="打开徽章铺">
        <div className="hall-badges-head"><span>馆员徽章</span><em>{ownedCount}/{badges.length} 枚</em></div>
        <div className="hall-badges-shelf">
          {badges.map((item) => {
            const owned = shelf.owned.includes(item.id);
            return <span key={item.id} className={`hall-badge-slot ${owned ? "is-owned" : ""} ${shelf.equipped === item.id ? "is-worn" : ""}`} title={owned ? item.name : `${item.name}，${item.price} 考据币`}><item.Icon size={15} /></span>;
          })}
        </div>
        <div className="hall-badges-cta"><span>{wornBadge ? `佩戴 ${wornBadge.name}` : "考据币换章"}</span><ChevronRight size={12} /></div>
      </button>
    </aside>

    <div className="hall-desk">
      <div className="hall-sr-only" role="status" aria-live="polite">{result ? `检索回执：${result.results.length ? `翻到 ${result.results.length} 份旧档` : "档案里没有对得上的记录"}` : ""}</div>
      {error && <div className="hall-error" id="hall-error" role="alert">{error}</div>}
      <form className={`hall-note ${error ? "is-invalid" : ""}`} onSubmit={submit}>
        <div className="hall-note-field">
          <div className="hall-note-meta">
            <label htmlFor="hall-query">写在纸条上，推给馆员</label>
            <span className="hall-note-count">{query.trim().length > 0 ? `${query.trim().length} 字` : ""}</span>
          </div>
          <textarea ref={inputRef} id="hall-query" rows={2} value={query} aria-invalid={Boolean(error)} aria-describedby={error ? "hall-error" : undefined} onChange={(event) => { searchSeq.current += 1; setPending(false); setReceiptOpen(false); setQuery(event.target.value); setListening(true); if (error) setError(""); if (result) setResult(null); }} onFocus={() => setListening(true)} onBlur={() => setListening(false)} onKeyDown={onNoteKeyDown} placeholder="例如：我想用自注意力替代循环结构，验证长距离依赖是否真的更好……" />
        </div>
        <button className="hall-push" type="submit" disabled={(!demo && !live) || pending}>
          {pending ? <LoaderCircle className="spin" size={17} /> : <ArrowRight size={17} />}{pending ? "查档中" : "推过去"}
        </button>
      </form>
      {!demo && !live && <div className="hall-error">本地服务未连接：现在只能查公开馆藏，启动 Compose 后可查自己的资料。</div>}
      <nav className="hall-actions" aria-label="档案馆快捷操作">
        <button onClick={() => inputRef.current?.focus()}><ScrollText size={14} />查一件想法</button>
        <button onClick={() => go("new")}><NotebookPen size={14} />正式考据</button>
        {!demo && <button onClick={() => go("sources")}><LibraryBig size={14} />我的馆藏</button>}
        <button onClick={() => go("report")}><FileText size={14} />取回旧裁决</button>
        <button onClick={() => go("project")}><BookOpen size={14} />技术档案</button>
      </nav>
    </div>

    {result && receiptOpen && <Receipt result={result} demo={demo} onClose={() => { setReceiptOpen(false); inputRef.current?.focus(); }} onAgain={() => {
      setReceiptOpen(false);
      setResult(null);
      setQuery("");
      if (error) setError("");
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }} onContinue={() => {
      if (!demo) {
        setReceiptOpen(false);
        onContinue(result.query);
        return;
      }
      setResult(null);
      setReceiptOpen(false);
      openSheet("precheck", result.query);
    }} />}

    {sheet && <HallArchivesSheet key={sheetKey} kind={sheet} seed={sheetSeed} onClose={returnToDesk} onSearch={() => searchFromSheet()} onSearchWith={searchFromSheet} />}
    {guideOpen && <HallGuide onClose={() => setGuideOpen(false)} />}
    {shopOpen && <BadgeShop coins={coins} shelf={shelf} onBuy={buyBadge} onEquip={equipBadge} onClose={closeShop} />}

    {menuOpen && <div className="hall-drawer-backdrop" onClick={() => setMenuOpen(false)}>
      <aside className="hall-drawer" onClick={(event) => event.stopPropagation()} aria-label="档案柜导航">
        <header><div><span>ARCHIVE DRAWER</span><strong>档案柜</strong></div><button onClick={() => setMenuOpen(false)} aria-label="关闭档案柜"><X size={18} /></button></header>
        {menuGroups.map((group) => <section key={group.label}>
          <span className="hall-drawer-label">{group.label}</span>
          {group.items.map((item) => <button key={item.id} onClick={() => { setMenuOpen(false); if (item.id === "guide") setGuideOpen(true); else if (item.id === "badges") setShopOpen(true); else go(item.id); }}>
            <item.icon size={17} />
            <span><strong>{item.label}</strong>{item.detail && <small>{item.detail}</small>}</span>
            <ChevronRight size={14} />
          </button>)}
        </section>)}
        <footer>
          <span className={`hall-status ${live ? "is-live" : "is-demo"}`}><i />{live ? "seekdb 与 PowerContext 在线" : demo ? "公开馆藏，浏览器实时检索" : "本地服务未连接"}</span>
          <a href="https://github.com/juanzhi-gcb/powercontext/tree/submit/qoder/qoder" target="_blank" rel="noreferrer">代码仓库<ArrowUpRight size={13} /></a>
        </footer>
      </aside>
    </div>}
  </div>;
}
