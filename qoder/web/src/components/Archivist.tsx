import { useEffect, useState } from "react";
import archivist from "../assets/archivist.png";

export type ArchivistMood = "idle" | "listen" | "think" | "found" | "blank" | "error" | "pleased";

const shortLabels: Record<ArchivistMood, string> = {
  idle: "值班",
  listen: "在听",
  think: "翻档中",
  found: "有出处",
  blank: "没翻到",
  error: "出错",
  pleased: "不错",
};

const moodEmoji: Record<ArchivistMood, string> = {
  idle: "💤",
  listen: "👂",
  think: "🕵️",
  found: "🥳",
  blank: "😔",
  error: "😰",
  pleased: "🎉",
};

function OpenEye({ side }: { side: "left" | "right" }) {
  const left = side === "left";
  const cx = left ? 249 : 357;
  const clip = `hero-eye-clip-${side}`;
  const shade = `hero-eye-shade-${side}`;
  const white = left
    ? "M226 220.5 C229 210 269 210 272 220.5 C269 231 229 231 226 220.5 Z"
    : "M334 220.5 C337 210 377 210 380 220.5 C377 231 337 231 334 220.5 Z";
  const lid = left
    ? "M226 220.5 C229 210 269 210 272 220.5"
    : "M334 220.5 C337 210 377 210 380 220.5";
  return <g className={`hero-eye hero-eye-${side}`}>
    <defs>
      <clipPath id={clip}><path d={white} /></clipPath>
      <linearGradient id={shade} gradientUnits="userSpaceOnUse" x1="0" y1="211" x2="0" y2="226">
        <stop offset="0" stopColor="#6d4630" stopOpacity=".24" />
        <stop offset=".8" stopColor="#6d4630" stopOpacity="0" />
      </linearGradient>
    </defs>
    <path d={white} fill="#eedfc7" stroke="#7a5036" strokeWidth=".7" strokeOpacity=".2" />
    <g clipPath={`url(#${clip})`}>
      <path d={white} fill={`url(#${shade})`} />
      <g className="hero-iris">
        <circle cx={cx} cy="222.4" r="10.3" fill="#64422c" />
        <circle cx={cx} cy="222.4" r="4.6" fill="#352116" />
        <circle cx={left ? cx - 3.2 : cx + 3.2} cy="217.4" r="1.8" fill="#fff8ec" opacity=".72" />
        <circle cx={left ? cx + 3.6 : cx - 3.6} cy="227" r="1.2" fill="#fff8ec" opacity=".18" />
      </g>
    </g>
    <path d={lid} fill="none" stroke="#3b2619" strokeWidth="2.8" strokeLinecap="round" />
  </g>;
}

function ShutEyes({ happy = false }: { happy?: boolean }) {
  return <g className="hero-eye-shut" fill="none" stroke="#3b2619" strokeWidth="3.5" strokeLinecap="round">
    {happy
      ? <><path d="M226 226 Q249 208 272 226" /><path d="M334 226 Q357 208 380 226" /></>
      : <><path d="M226 219 Q249 234 272 219" /><path d="M334 219 Q357 234 380 219" /></>}
  </g>;
}

function Mouth({ mood }: { mood: ArchivistMood }) {
  if (mood !== "think" && mood !== "blank" && mood !== "error") return null;
  const path = mood === "error" ? "M290 286 Q306 275 322 286" : mood === "blank" ? "M292 282 Q306 279 320 282" : "M294 283 Q306 278 318 283";
  return <g className={`hero-mouth hero-mouth-${mood}`}>
    <path d="M265 272 Q306 299 347 272" fill="none" stroke="url(#heroSkinMouth)" strokeWidth="11.5" strokeLinecap="round" filter="url(#heroSoft)" />
    <path d={path} fill="none" stroke="#8a5a3f" strokeWidth="3.4" strokeLinecap="round" />
  </g>;
}

export function Archivist({ mood }: { mood: ArchivistMood }) {
  const [blinking, setBlinking] = useState(false);
  const happy = mood === "pleased";
  const eyesOpen = mood !== "idle" && mood !== "listen";
  const eyesShut = blinking && !happy;

  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    let openTimer = 0;
    let closeTimer = 0;
    const schedule = () => {
      openTimer = window.setTimeout(() => {
        setBlinking(true);
        closeTimer = window.setTimeout(() => {
          setBlinking(false);
          schedule();
        }, 150);
      }, 2800 + Math.random() * 3600);
    };
    schedule();
    return () => {
      window.clearTimeout(openTimer);
      window.clearTimeout(closeTimer);
    };
  }, []);

  return <div className={`hall-hero mood-${mood}`}>
    <img className="hall-hero-art" src={archivist} alt="夜班馆员老余" />
    <svg className="hall-hero-face" viewBox="0 0 460 690" aria-hidden="true">
      <defs>
        <linearGradient id="heroSkinEye" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ecc39c" />
          <stop offset="1" stopColor="#e3b189" />
        </linearGradient>
        <linearGradient id="heroSkinMouth" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#e1ae82" />
          <stop offset="1" stopColor="#daa579" />
        </linearGradient>
        <filter id="heroSoft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1" /></filter>
        <filter id="heroBlush" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2" /></filter>
      </defs>

      {eyesOpen && <g fill="none" stroke="url(#heroSkinEye)" strokeWidth="10.5" strokeLinecap="round" filter="url(#heroSoft)">
        <path d="M223 217 Q249 233 275 217" />
        <path d="M331 218 Q357 233 383 218" />
      </g>}

      {happy
        ? <><g className="hero-eye-shut" fill="none" stroke="#3b2619" strokeWidth="3.5" strokeLinecap="round">
          <path d="M226 226 Q249 208 272 226" />
        </g><OpenEye side="right" /></>
        : !eyesOpen
          ? null
          : eyesShut
            ? <ShutEyes />
            : <><OpenEye side="left" /><OpenEye side="right" /></>}

      <Mouth mood={mood} />

      {(mood === "found" || happy) && <g className="hero-blush" fill="#cf7a5e" opacity=".26" filter="url(#heroBlush)">
        <ellipse cx="223" cy="258" rx="19" ry="8" />
        <ellipse cx="385" cy="258" rx="19" ry="8" />
      </g>}

      {(mood === "found" || happy) && <g className="hero-sparkles" fill="#f2d08a">
        <path d="M414 158 l2.6 7.4 7.4 2.6 -7.4 2.6 -2.6 7.4 -2.6 -7.4 -7.4 -2.6 7.4 -2.6z" />
        <path d="M178 192 l2 5.6 5.6 2 -5.6 2 -2 5.6 -2 -5.6 -5.6 -2 5.6 -2z" />
      </g>}

      {mood === "error" && <path className="hero-sweat" d="M236 268 q9 14 0 20 q-9 -6 0 -20" fill="#9fc6cf" opacity=".9" />}
    </svg>
    <div className="hall-mood" key={mood} role="status" aria-live="polite">
      <span className="hall-thought-big">
        <span className="hall-mood-emoji" aria-hidden="true">{moodEmoji[mood]}</span>
        <span className="hall-mood-label">{shortLabels[mood]}</span>
      </span>
      <span className="hall-thought-mid" aria-hidden="true" />
      <span className="hall-thought-small" aria-hidden="true" />
    </div>
  </div>;
}
