import { useState, useEffect } from "react";

const WORDMARK_LETTERS = [
  { char: "N", isGreen: false },
  { char: "O", isGreen: false },
  { char: "Q", isGreen: true },
  { char: "U", isGreen: true },
  { char: "E", isGreen: true },
  { char: "U", isGreen: true },
  { char: "E", isGreen: true },
];

export default function SplashScreen({ onFinish }) {
  const [isLeaving, setIsLeaving] = useState(false);

  useEffect(() => {
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Transition stages:
    // If reduced motion: finish quickly (700ms total)
    // Normal: exit starts at 2700ms, finished and unmounted at 3150ms
    const exitTimer = setTimeout(
      () => {
        setIsLeaving(true);
      },
      prefersReducedMotion ? 450 : 2700
    );

    const finishTimer = setTimeout(
      () => {
        if (onFinish) onFinish();
      },
      prefersReducedMotion ? 700 : 3150
    );

    return () => {
      clearTimeout(exitTimer);
      clearTimeout(finishTimer);
    };
  }, [onFinish]);

  return (
    <div
      className={`splash-screen ${isLeaving ? "splash-leaving" : ""}`}
      aria-label="NoQueue intro animation"
      role="status"
    >
      <div className="splash-ambient-glow" aria-hidden="true" />
      <div className="splash-content">
        {/* Stage 1: Logo Entrance */}
        <div className="splash-logo">
          <img
            src="/logo-icon.png"
            alt="NoQueue Logo"
            className="splash-logo-img"
          />
        </div>

        {/* Stage 2: Letter-by-letter Wordmark */}
        <div className="splash-wordmark" aria-label="NOQUEUE">
          {WORDMARK_LETTERS.map((item, index) => (
            <span
              key={index}
              className={`splash-letter ${
                item.isGreen ? "splash-letter-green" : "splash-letter-dark"
              }`}
              style={{
                animationDelay: `${0.6 + index * 0.14}s`,
              }}
            >
              {item.char}
            </span>
          ))}
        </div>

        {/* Stage 3: Tagline */}
        <div className="splash-tagline">
          <span>SMART CNG QUEUE PREDICTION &amp; MOBILITY ASSISTANT</span>
        </div>
      </div>
    </div>
  );
}

