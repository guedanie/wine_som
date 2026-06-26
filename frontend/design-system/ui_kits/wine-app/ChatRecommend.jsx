// Screen 2 — Conversational recommendations (chat + wine cards).
function ChatRecommend({ prefs, wines, onOpenWine }) {
  const [input, setInput] = React.useState("");
  const followups = ["Anything from Burgundy?", "What about under $30?", "Something to cellar"];

  const Bubble = ({ children }) => (
    <div style={{ display: "flex", gap: 11, alignItems: "flex-start", marginBottom: 14 }}>
      <div style={{ width: 32, height: 32, borderRadius: "50%", flex: "none", background: "var(--bordeaux)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Stamp size={20} reversed />
      </div>
      <div style={{ background: "var(--cream-raised)", border: "1px solid var(--border)", borderRadius: "4px 14px 14px 14px", padding: "13px 15px", fontFamily: "var(--font-sans)", fontSize: 14, lineHeight: 1.55, color: "var(--ink-2)" }}>{children}</div>
    </div>
  );
  const UserBubble = ({ children }) => (
    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 14 }}>
      <div style={{ background: "var(--bordeaux)", color: "var(--cream)", borderRadius: "14px 4px 14px 14px", padding: "11px 15px", fontSize: 14, lineHeight: 1.5, maxWidth: "78%" }}>{children}</div>
    </div>
  );

  return (
    <div style={{ display: "flex", height: "100%", minHeight: 640 }}>
      {/* Chat */}
      <div style={{ width: "44%", borderRight: "1.5px solid var(--ink)", display: "flex", flexDirection: "column", background: "var(--cream)" }}>
        <div style={{ padding: "20px 24px 14px", borderBottom: "1px solid var(--border)" }}>
          <Eyebrow>The sommelier</Eyebrow>
          <div style={{ fontFamily: "var(--font-serif)", fontSize: 24, color: "var(--ink)", marginTop: 4 }}>Tonight, near {prefs.zip}</div>
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
          <UserBubble>{prefs.styles.join(", ")} · under ${prefs.budget} · {prefs.occasion.toLowerCase()}</UserBubble>
          <Bubble>
            Good brief. You want something with <strong style={{ color: "var(--bordeaux)" }}>weight and grip</strong> that won't break ${prefs.budget} — here are three drinking well right now near you.
          </Bubble>
          <Bubble>
            I'd start with the <strong style={{ color: "var(--bordeaux)" }}>Esprit de Tablas</strong>. Rhône grapes grown in Paso Robles — dark cherry, garrigue and leather, serious but generous. Spec's has it for $55, four miles away. If you'd rather go Italian, the Brunello is the more structured, age-worthy pick.
          </Bubble>
        </div>
        {/* Composer */}
        <div style={{ borderTop: "1px solid var(--border)", padding: "14px 24px 18px" }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
            {followups.map((f) => (
              <button key={f} onClick={() => setInput(f)} style={{ cursor: "pointer", fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--bordeaux)", background: "var(--bordeaux-tint)", border: "none", borderRadius: 999, padding: "6px 12px" }}>{f}</button>
            ))}
          </div>
          <div style={{ display: "flex", border: "1.5px solid var(--ink)", background: "var(--cream-raised)" }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a follow-up…"
              style={{ flex: 1, border: "none", background: "transparent", outline: "none", fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--ink)", padding: "11px 13px" }} />
            <button style={{ border: "none", background: "var(--bordeaux)", color: "var(--cream)", padding: "0 16px", cursor: "pointer", fontSize: 16 }}>→</button>
          </div>
        </div>
      </div>

      {/* Wine cards */}
      <div style={{ flex: 1, background: "var(--paper)", overflow: "auto", padding: "24px 28px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 18 }}>
          <span className="t-eyebrow">3 wines for you</span>
          <span style={{ fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--faded)" }}>within 15 mi · in stock</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
          {wines.map((w) => <WineCard key={w.id} wine={w} onOpen={() => onOpenWine(w)} />)}
        </div>
      </div>
    </div>
  );
}
Object.assign(window, { ChatRecommend });
