import { useState, useRef, useEffect } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

/* ─────────────────────────────────────────────────────────
   Score Ring  (animated SVG circle)
───────────────────────────────────────────────────────── */
function ScoreRing({ score }) {
  const [display, setDisplay] = useState(0);
  const R = 52, C = 2 * Math.PI * R;
  const color = score >= 75 ? "#6affb4" : score >= 55 ? "#fbbf24" : "#f87171";
  const label = score >= 75 ? "STRONG MATCH" : score >= 55 ? "PARTIAL MATCH" : "NEEDS WORK";

  useEffect(() => {
    let start = null, dur = 1200;
    const tick = (ts) => {
      if (!start) start = ts;
      const p = Math.min((ts - start) / dur, 1);
      setDisplay(Math.round(p * score));
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [score]);

  return (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:10 }}>
      <svg width={130} height={130} viewBox="0 0 130 130">
        {/* track */}
        <circle cx={65} cy={65} r={R} fill="none" stroke="#1a1a24" strokeWidth={10}/>
        {/* filled arc */}
        <circle cx={65} cy={65} r={R} fill="none"
          stroke={color} strokeWidth={10}
          strokeDasharray={`${(display/100)*C} ${C}`}
          strokeLinecap="round"
          transform="rotate(-90 65 65)"
          style={{transition:"stroke-dasharray .05s linear"}}/>
        {/* number */}
        <text x={65} y={60} textAnchor="middle" dominantBaseline="central"
          fill="white" fontSize={26} fontWeight={800}
          fontFamily="'Syne',sans-serif">{display}</text>
        <text x={65} y={80} textAnchor="middle" dominantBaseline="central"
          fill="#7070a0" fontSize={11} fontFamily="'DM Mono',monospace">/100</text>
      </svg>
      <span style={{
        fontFamily:"'DM Mono',monospace", fontSize:11, letterSpacing:"0.12em",
        color, padding:"3px 12px", borderRadius:20,
        background:`${color}18`, border:`1px solid ${color}40`
      }}>{label}</span>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Bar
───────────────────────────────────────────────────────── */
function Bar({ label, score, delay = 0 }) {
  const [w, setW] = useState(0);
  const color = score >= 75 ? "#6affb4" : score >= 55 ? "#fbbf24" : "#f87171";
  useEffect(() => {
    const t = setTimeout(() => setW(score), delay);
    return () => clearTimeout(t);
  }, [score, delay]);
  return (
    <div style={{ marginBottom:12 }}>
      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:5 }}>
        <span style={{ fontSize:12, color:"#7070a0", fontFamily:"'DM Mono',monospace", letterSpacing:"0.06em" }}>
          {label.replace(/_/g," ").toUpperCase()}
        </span>
        <span style={{ fontSize:13, fontWeight:600, color, fontFamily:"'DM Mono',monospace" }}>{score}%</span>
      </div>
      <div style={{ height:5, background:"#1a1a24", borderRadius:3, overflow:"hidden" }}>
        <div style={{
          height:"100%", width:`${w}%`, background:color,
          borderRadius:3, transition:`width 0.9s cubic-bezier(.4,0,.2,1) ${delay}ms`
        }}/>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Keyword chip
───────────────────────────────────────────────────────── */
function Chip({ text, type }) {
  const map = {
    present:          { bg:"#6affb418", bd:"#6affb440", cl:"#6affb4" },
    missing_critical: { bg:"#f8717118", bd:"#f8717140", cl:"#f87171" },
    missing_important:{ bg:"#fbbf2418", bd:"#fbbf2440", cl:"#fbbf24" },
    missing_nice:     { bg:"#a78bfa18", bd:"#a78bfa40", cl:"#a78bfa" },
  };
  const s = map[type] || map.missing_nice;
  return (
    <span style={{
      display:"inline-block", padding:"3px 10px", margin:"3px 3px",
      borderRadius:12, fontSize:12, fontFamily:"'DM Mono',monospace",
      background:s.bg, border:`1px solid ${s.bd}`, color:s.cl,
    }}>{text}</span>
  );
}

/* ─────────────────────────────────────────────────────────
   Loading spinner
───────────────────────────────────────────────────────── */
const STEPS = [
  "Agent 1 — parsing your resume…",
  "Agent 2 — extracting JD requirements…",
  "Agent 3 — running gap analysis…",
  "Agent 4 — rewriting bullet points…",
];
function Loader() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStep(s => Math.min(s+1, STEPS.length-1)), 4000);
    return () => clearInterval(t);
  }, []);
  return (
    <div style={{
      background:"var(--surface)", border:"1px solid var(--border)",
      borderRadius:14, padding:"32px 28px"
    }}>
      {STEPS.map((s, i) => (
        <div key={i} style={{
          display:"flex", alignItems:"center", gap:14,
          marginBottom:16, opacity: i > step ? 0.25 : 1,
          transition:"opacity 0.4s"
        }}>
          <div style={{
            width:8, height:8, borderRadius:"50%",
            background: i < step ? "#6affb4" : i === step ? "#6affb4" : "var(--border2)",
            animation: i === step ? "pulse 1.2s infinite" : "none",
            flexShrink:0
          }}/>
          <span style={{
            fontSize:13, fontFamily:"'DM Mono',monospace",
            color: i < step ? "#6affb4" : i === step ? "var(--text)" : "var(--muted)"
          }}>{s}</span>
          {i < step && <span style={{ marginLeft:"auto", fontSize:11, color:"#6affb4" }}>✓</span>}
        </div>
      ))}
      <div style={{
        marginTop:20, height:2, background:"var(--surface2)", borderRadius:1, overflow:"hidden"
      }}>
        <div style={{
          height:"100%", background:"#6affb4", borderRadius:1,
          width:`${(step+1)/STEPS.length*100}%`,
          transition:"width 4s linear"
        }}/>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Main App
───────────────────────────────────────────────────────── */
export default function App() {
  const [mode, setMode]       = useState("file");   // "file" | "text"
  const [file, setFile]       = useState(null);
  const [resumeTxt, setResumeTxt] = useState("");
  const [jd, setJd]           = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState(null);
  const [err, setErr]         = useState("");
  const [tab, setTab]         = useState("score");
  const fileRef               = useRef();

  const analyze = async () => {
    if (!jd.trim()) { setErr("Paste a job description."); return; }
    if (mode==="file" && !file)       { setErr("Upload your resume."); return; }
    if (mode==="text" && !resumeTxt.trim()) { setErr("Paste your resume text."); return; }
    setErr(""); setLoading(true); setResult(null);
    try {
      const fd = new FormData();
      fd.append("job_description", jd);
      if (mode==="file") fd.append("resume_file", file);
      else               fd.append("resume_text", resumeTxt);
      const res = await fetch(`${API}/analyze`, { method:"POST", body:fd });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      setResult(data);
      setTab("score");
    } catch(e) {
      setErr(e.message || "Analysis failed — is the backend running?");
    } finally { setLoading(false); }
  };

  const TABS = [
    { id:"score",    label:"Score" },
    { id:"gaps",     label:"Keyword Gaps" },
    { id:"wins",     label:"Quick Wins" },
    { id:"rewrites", label:"Rewrites" },
  ];

  /* ── Render ── */
  return (
    <div style={{ minHeight:"100vh" }}>

      {/* ── Top bar ─────────────────────────────────────── */}
      <header style={{
        borderBottom:"1px solid var(--border)",
        padding:"0 32px",
        height:56,
        display:"flex", alignItems:"center", justifyContent:"space-between",
        position:"sticky", top:0, zIndex:100,
        background:"rgba(10,10,15,.9)", backdropFilter:"blur(12px)"
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:10 }}>
          <div style={{ width:28, height:28, background:"#6affb4", borderRadius:7, display:"flex", alignItems:"center", justifyContent:"center" }}>
            <svg width={16} height={16} viewBox="0 0 16 16" fill="none">
              <rect x={2} y={5} width={12} height={9} rx={2} stroke="#0a0a0f" strokeWidth={1.8}/>
              <path d="M5 5V4a3 3 0 016 0v1" stroke="#0a0a0f" strokeWidth={1.8} strokeLinecap="round"/>
              <line x1={8} y1={8} x2={8} y2={11} stroke="#0a0a0f" strokeWidth={1.8} strokeLinecap="round"/>
              <line x1={6} y1={9.5} x2={10} y2={9.5} stroke="#0a0a0f" strokeWidth={1.8} strokeLinecap="round"/>
            </svg>
          </div>
          <span style={{ fontFamily:"'Syne',sans-serif", fontWeight:800, fontSize:18, letterSpacing:"-0.02em" }}>
            Job<span style={{ color:"#6affb4" }}>Fit</span>
          </span>
        </div>
      </header>

      <main style={{ maxWidth:920, margin:"0 auto", padding:"40px 24px 80px" }}>

        {/* ── Hero ─────────────────────────────────────── */}
        {!result && !loading && (
          <div style={{ textAlign:"center", marginBottom:48 }} className="fade-up">
            <div style={{
              fontFamily:"'DM Mono',monospace", fontSize:11, color:"#6affb4",
              letterSpacing:"0.2em", marginBottom:16
            }}>MATCH · TAILOR · APPLY</div>
            <h1 style={{
              fontFamily:"'Syne',sans-serif", fontWeight:800,
              fontSize:"clamp(32px,5vw,54px)", lineHeight:1.1,
              letterSpacing:"-0.03em", marginBottom:16
            }}>
              Stop getting filtered out<br/>
              <span style={{ color:"#6affb4" }}>before humans see you.</span>
            </h1>
            <p style={{ color:"var(--muted)", fontSize:15, maxWidth:500, margin:"0 auto" }}>
              Paste your resume and a job description. JobFit scores your match,
              surfaces every keyword gap, and rewrites your bullets for that role.
            </p>
          </div>
        )}

        {/* ── Input grid ───────────────────────────────── */}
        {!result && !loading && (
          <div style={{
            display:"grid", gridTemplateColumns:"1fr 1fr",
            gap:20, marginBottom:20
          }} className="fade-up">

            {/* Resume panel */}
            <div style={{
              background:"var(--surface)", border:"1px solid var(--border)",
              borderRadius:14, padding:22
            }}>
              <div style={{
                display:"flex", alignItems:"center",
                justifyContent:"space-between", marginBottom:16
              }}>
                <span style={{
                  fontFamily:"'DM Mono',monospace", fontSize:11,
                  color:"var(--muted)", letterSpacing:"0.12em"
                }}>YOUR RESUME</span>
                <div style={{ display:"flex", gap:6 }}>
                  {["file","text"].map(m => (
                    <button key={m} onClick={()=>setMode(m)} style={{
                      padding:"4px 12px", borderRadius:8, fontSize:11,
                      fontFamily:"'DM Mono',monospace", letterSpacing:"0.06em",
                      background: mode===m ? "#6affb418" : "transparent",
                      border: `1px solid ${mode===m ? "#6affb4" : "var(--border)"}`,
                      color: mode===m ? "#6affb4" : "var(--muted)",
                      transition:"all .2s"
                    }}>{m==="file"?"UPLOAD":"PASTE"}</button>
                  ))}
                </div>
              </div>

              {mode==="file" ? (
                <div
                  onClick={()=>fileRef.current.click()}
                  style={{
                    border:"2px dashed var(--border2)", borderRadius:10,
                    padding:"36px 20px", textAlign:"center", cursor:"pointer",
                    transition:"border-color .2s, background .2s"
                  }}
                  onMouseEnter={e=>{e.currentTarget.style.borderColor="#6affb4"; e.currentTarget.style.background="#6affb408"}}
                  onMouseLeave={e=>{e.currentTarget.style.borderColor="var(--border2)"; e.currentTarget.style.background="transparent"}}
                >
                  <div style={{ fontSize:28, marginBottom:10 }}>📄</div>
                  <div style={{ color:"var(--muted)", fontSize:13 }}>
                    {file ? (
                      <span style={{ color:"#6affb4" }}>✓ {file.name}</span>
                    ) : "Click to upload PDF, DOCX, or TXT"}
                  </div>
                  <input ref={fileRef} type="file" accept=".pdf,.docx,.txt"
                    style={{ display:"none" }}
                    onChange={e=>setFile(e.target.files[0])}/>
                </div>
              ) : (
                <textarea value={resumeTxt} onChange={e=>setResumeTxt(e.target.value)}
                  placeholder="Paste your full resume text here…"
                  style={{
                    width:"100%", minHeight:180, background:"var(--surface2)",
                    border:"1px solid var(--border)", borderRadius:8,
                    padding:14, color:"var(--text)", fontSize:12,
                    resize:"vertical", outline:"none",
                    transition:"border-color .2s", boxSizing:"border-box"
                  }}
                  onFocus={e=>e.target.style.borderColor="#6affb4"}
                  onBlur={e=>e.target.style.borderColor="var(--border)"}
                />
              )}
            </div>

            {/* JD panel */}
            <div style={{
              background:"var(--surface)", border:"1px solid var(--border)",
              borderRadius:14, padding:22
            }}>
              <div style={{
                fontFamily:"'DM Mono',monospace", fontSize:11,
                color:"var(--muted)", letterSpacing:"0.12em", marginBottom:16
              }}>JOB DESCRIPTION</div>
              <textarea value={jd} onChange={e=>setJd(e.target.value)}
                placeholder="Paste the full job description here — including required skills, responsibilities, and qualifications…"
                style={{
                  width:"100%", minHeight:210, background:"var(--surface2)",
                  border:"1px solid var(--border)", borderRadius:8,
                  padding:14, color:"var(--text)", fontSize:12,
                  resize:"vertical", outline:"none",
                  transition:"border-color .2s", boxSizing:"border-box"
                }}
                onFocus={e=>e.target.style.borderColor="#6affb4"}
                onBlur={e=>e.target.style.borderColor="var(--border)"}
              />
            </div>
          </div>
        )}

        {/* ── Analyze button ───────────────────────────── */}
        {!result && !loading && (
          <button onClick={analyze} className="fade-up" style={{
            width:"100%", padding:16,
            background:"#6affb4", color:"#0a0a0f",
            border:"none", borderRadius:12,
            fontSize:15, fontWeight:800, letterSpacing:"0.06em",
            fontFamily:"'Syne',sans-serif",
            transition:"transform .15s, box-shadow .15s",
            boxShadow:"0 0 0 0 #6affb440",
            marginBottom:err ? 16 : 0
          }}
          onMouseEnter={e=>{e.target.style.transform="translateY(-2px)"; e.target.style.boxShadow="0 8px 32px #6affb440"}}
          onMouseLeave={e=>{e.target.style.transform="none"; e.target.style.boxShadow="none"}}
          >
            ⚡ ANALYSE MY RESUME
          </button>
        )}

        {err && (
          <div style={{
            background:"#f8717112", border:"1px solid #f87171",
            borderRadius:8, padding:"12px 16px",
            color:"#f87171", fontSize:13,
            fontFamily:"'DM Mono',monospace", marginBottom:16
          }}>⚠ {err}</div>
        )}

        {/* ── Loader ───────────────────────────────────── */}
        {loading && (
          <div className="fade-up"><Loader /></div>
        )}

        {/* ── Results ──────────────────────────────────── */}
        {result && !loading && (
          <div className="fade-up">

            {/* Re-analyze button */}
            <button onClick={()=>{ setResult(null); setErr(""); }}
              style={{
                marginBottom:20, padding:"8px 18px",
                background:"transparent", border:"1px solid var(--border2)",
                borderRadius:8, color:"var(--muted)", fontSize:12,
                fontFamily:"'DM Mono',monospace", letterSpacing:"0.08em",
                transition:"all .2s"
              }}
              onMouseEnter={e=>{e.target.style.borderColor="#6affb4"; e.target.style.color="#6affb4"}}
              onMouseLeave={e=>{e.target.style.borderColor="var(--border2)"; e.target.style.color="var(--muted)"}}
            >← NEW ANALYSIS</button>

            {/* Tab bar */}
            <div style={{
              display:"flex", borderBottom:"1px solid var(--border)",
              marginBottom:0, overflowX:"auto"
            }}>
              {TABS.map(t => (
                <button key={t.id} onClick={()=>setTab(t.id)} style={{
                  padding:"12px 22px", background:"transparent", border:"none",
                  borderBottom: tab===t.id ? "2px solid #6affb4" : "2px solid transparent",
                  color: tab===t.id ? "#6affb4" : "var(--muted)",
                  fontSize:13, fontFamily:"'DM Mono',monospace",
                  letterSpacing:"0.06em", whiteSpace:"nowrap",
                  transition:"color .2s"
                }}>{t.label.toUpperCase()}</button>
              ))}
            </div>

            <div style={{
              background:"var(--surface)", border:"1px solid var(--border)",
              borderTop:"none", borderRadius:"0 0 14px 14px", padding:28
            }}>

              {/* ══ SCORE TAB ══════════════════════════ */}
              {tab==="score" && (
                <div>
                  <div style={{ display:"flex", gap:36, alignItems:"flex-start", flexWrap:"wrap" }}>
                    <ScoreRing score={result.match_score || 0}/>
                    <div style={{ flex:1, minWidth:200 }}>
                      <div style={{ fontFamily:"'DM Mono',monospace", fontSize:10,
                        color:"var(--muted)", letterSpacing:"0.15em", marginBottom:14 }}>
                        SECTION BREAKDOWN
                      </div>
                      {Object.entries(result.section_scores || {}).map(([k,v],i) => (
                        <Bar key={k} label={k} score={v} delay={i*120}/>
                      ))}
                    </div>
                  </div>

                  {result.honest_assessment && (
                    <div style={{
                      marginTop:24, background:"var(--surface2)", borderRadius:10, padding:18,
                      borderLeft:"3px solid #6affb4"
                    }}>
                      <div style={{ fontFamily:"'DM Mono',monospace", fontSize:10,
                        color:"#6affb4", letterSpacing:"0.15em", marginBottom:8 }}>
                        HONEST ASSESSMENT
                      </div>
                      <p style={{ fontSize:14, color:"#c0c0d8", lineHeight:1.7 }}>
                        {result.honest_assessment}
                      </p>
                    </div>
                  )}

                  {result.strengths?.length > 0 && (
                    <div style={{ marginTop:20 }}>
                      <div style={{ fontFamily:"'DM Mono',monospace", fontSize:10,
                        color:"var(--muted)", letterSpacing:"0.15em", marginBottom:10 }}>
                        ✓ STRENGTHS
                      </div>
                      {result.strengths.map((s,i) => (
                        <div key={i} style={{ display:"flex", gap:10, marginBottom:8, alignItems:"flex-start" }}>
                          <span style={{ color:"#6affb4", flexShrink:0 }}>▸</span>
                          <span style={{ fontSize:13, color:"#a0a0c0", lineHeight:1.5 }}>{s}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ══ GAPS TAB ══════════════════════════ */}
              {tab==="gaps" && (
                <div>
                  {result.present_keywords?.length > 0 && (
                    <div style={{ marginBottom:28 }}>
                      <div style={{ fontFamily:"'DM Mono',monospace", fontSize:10,
                        color:"#6affb4", letterSpacing:"0.15em", marginBottom:12 }}>
                        ✓ ALREADY IN YOUR RESUME
                      </div>
                      <div>{result.present_keywords.map(k=><Chip key={k} text={k} type="present"/>)}</div>
                    </div>
                  )}

                  {result.missing_keywords?.length > 0 && (
                    <div>
                      <div style={{ fontFamily:"'DM Mono',monospace", fontSize:10,
                        color:"var(--muted)", letterSpacing:"0.15em", marginBottom:14 }}>
                        ✗ MISSING KEYWORDS — ranked by importance
                      </div>
                      <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
                        {result.missing_keywords.map((item,i) => {
                          const kw = typeof item === "string" ? item : item.keyword;
                          const imp = item.importance || "nice-to-have";
                          const type = imp==="critical" ? "missing_critical"
                                     : imp==="important" ? "missing_important"
                                     : "missing_nice";
                          return (
                            <div key={i} style={{
                              background:"var(--surface2)", borderRadius:10,
                              padding:16, border:"1px solid var(--border)"
                            }}>
                              <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:item.suggested_placement?8:0 }}>
                                <Chip text={kw} type={type}/>
                                {item.frequency_in_jd > 0 && (
                                  <span style={{ fontSize:11, color:"var(--muted)",
                                    fontFamily:"'DM Mono',monospace" }}>
                                    {item.frequency_in_jd}× in JD
                                  </span>
                                )}
                              </div>
                              {item.suggested_placement && (
                                <div style={{ fontSize:12, color:"#7070a0",
                                  fontFamily:"'DM Mono',monospace", marginBottom:4 }}>
                                  💡 {item.suggested_placement}
                                </div>
                              )}
                              {item.context && (
                                <div style={{ fontSize:12, color:"var(--muted)", fontStyle:"italic" }}>
                                  {item.context}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ══ QUICK WINS TAB ═════════════════════ */}
              {tab==="wins" && (
                <div>
                  {result.quick_wins?.map((w,i) => (
                    <div key={i} style={{
                      display:"flex", gap:16, alignItems:"flex-start",
                      background:"var(--surface2)", borderRadius:10,
                      padding:18, marginBottom:12, border:"1px solid var(--border)"
                    }}>
                      <div style={{
                        width:30, height:30, borderRadius:"50%",
                        background:"#6affb418", border:"1px solid #6affb4",
                        color:"#6affb4", fontSize:13, fontWeight:800,
                        fontFamily:"'Syne',sans-serif",
                        display:"flex", alignItems:"center", justifyContent:"center",
                        flexShrink:0
                      }}>{i+1}</div>
                      <div>
                        <div style={{ fontSize:14, color:"var(--text)", marginBottom:8, lineHeight:1.5 }}>
                          {w.action}
                        </div>
                        <div style={{ display:"flex", gap:16 }}>
                          {w.impact && (
                            <span style={{ fontSize:12, color:"#6affb4",
                              fontFamily:"'DM Mono',monospace" }}>↑ {w.impact}</span>
                          )}
                          {w.effort && (
                            <span style={{ fontSize:12, color:"var(--muted)",
                              fontFamily:"'DM Mono',monospace" }}>⏱ {w.effort}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}

                  {result.score_to_75?.length > 0 && (
                    <div style={{ marginTop:24 }}>
                      <div style={{ fontFamily:"'DM Mono',monospace", fontSize:10,
                        color:"#fbbf24", letterSpacing:"0.15em", marginBottom:12 }}>
                        ⭐ TO REACH 75%+ MATCH
                      </div>
                      {result.score_to_75.map((s,i)=>(
                        <div key={i} style={{
                          display:"flex", gap:10, marginBottom:8,
                          fontSize:13, color:"#d0b040", lineHeight:1.5
                        }}>
                          <span style={{ flexShrink:0 }}>▸</span>{s}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ══ REWRITES TAB ══════════════════════ */}
              {tab==="rewrites" && (
                <div>
                  {result.summary_suggestion && (
                    <div style={{ marginBottom:24 }}>
                      <div style={{ fontFamily:"'DM Mono',monospace", fontSize:10,
                        color:"var(--muted)", letterSpacing:"0.15em", marginBottom:10 }}>
                        SUGGESTED PROFILE SUMMARY
                      </div>
                      <div style={{
                        background:"var(--surface2)", borderRadius:10,
                        padding:18, border:"1px solid #6affb440",
                        fontSize:14, color:"#c0c0d8", lineHeight:1.7,
                        fontStyle:"italic"
                      }}>
                        "{result.summary_suggestion}"
                      </div>
                    </div>
                  )}

                  {result.rewritten_bullets?.length > 0 && (
                    <div>
                      <div style={{ fontFamily:"'DM Mono',monospace", fontSize:10,
                        color:"var(--muted)", letterSpacing:"0.15em", marginBottom:14 }}>
                        REWRITTEN BULLET POINTS
                      </div>
                      {result.rewritten_bullets.map((item,i)=>(
                        <div key={i} style={{
                          background:"var(--surface2)", borderRadius:12,
                          padding:18, marginBottom:14, border:"1px solid var(--border)"
                        }}>
                          <div style={{ marginBottom:12 }}>
                            <div style={{ fontFamily:"'DM Mono',monospace", fontSize:9,
                              color:"var(--muted)", letterSpacing:"0.15em", marginBottom:6 }}>
                              ORIGINAL
                            </div>
                            <div style={{ fontSize:13, color:"var(--muted)", lineHeight:1.6 }}>
                              {item.original}
                            </div>
                          </div>
                          <div style={{ borderTop:"1px solid var(--border)", paddingTop:12 }}>
                            <div style={{ fontFamily:"'DM Mono',monospace", fontSize:9,
                              color:"#6affb4", letterSpacing:"0.15em", marginBottom:6 }}>
                              ✦ REWRITTEN
                            </div>
                            <div style={{ fontSize:13, color:"var(--text)", lineHeight:1.6, marginBottom:10 }}>
                              {item.rewritten}
                            </div>
                            {item.keywords_added?.length > 0 && (
                              <div style={{ display:"flex", flexWrap:"wrap", gap:4 }}>
                                {item.keywords_added.map(k=>(
                                  <span key={k} style={{
                                    fontSize:10, padding:"2px 8px", borderRadius:10,
                                    background:"#6affb418", border:"1px solid #6affb430",
                                    color:"#6affb4", fontFamily:"'DM Mono',monospace"
                                  }}>{k}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

            </div>{/* panel */}
          </div>
        )}

        {/* ── Footer ───────────────────────────────────── */}
        <footer style={{ marginTop:60, textAlign:"center" }}>
          <p style={{ fontSize:11, color:"var(--muted)",
            fontFamily:"'DM Mono',monospace", letterSpacing:"0.08em" }}>
            © 2026 JobFit. All rights reserved.
          </p>
        </footer>
      </main>
    </div>
  );
}
