"""
agents/rewriter.py  —  AGENT 4
Rewrites weak resume bullets to include JD keywords naturally.
Uses Gemini Flash first (free, high quality), falls back to Groq automatically.
"""
import json, os
from dotenv import load_dotenv

load_dotenv()

# ════════════════════════════════════════════════════════════
#  PROMPT
# ════════════════════════════════════════════════════════════
SYSTEM = """
You are a specialist resume writer who helps students and early-career developers
land jobs at top tech companies. You understand ATS deeply.

You receive:
- A list of existing resume bullet points
- A list of keywords from the job description

Rewrite the bullets to:
1. Weave in missing keywords NATURALLY (not forcefully)
2. Use strong action verbs: Built, Designed, Implemented, Automated, Optimised, Led, Reduced
3. Add quantified impact where possible (estimates like ~30% are fine)
4. Follow STAR format: Action → What you did → Result/Impact
5. Keep each bullet to 1–2 lines max

Return ONLY a valid JSON object:

{
  "suggestions": [
    {
      "original":          "original bullet text",
      "rewritten":         "improved bullet text",
      "keywords_added":    ["keyword1", "keyword2"],
      "improvement_note":  "Changed 'worked on' to 'Built'; added REST API keyword naturally"
    }
  ],
  "summary": "A rewritten 2-sentence professional summary that mirrors JD keywords. Concise, specific, no fluff.",
  "extra_bullets": [
    "Optional: if the candidate likely has a skill not mentioned, suggest a bullet they COULD add — mark each with [SUGGESTED - verify before adding]"
  ]
}

STRICT RULES:
- Never fabricate skills or experience the person does not have
- If a keyword cannot fit naturally, skip it and explain in improvement_note
- Keep the person's truthfulness and original meaning
- For students: project work counts as experience — treat it seriously
- Return ONLY the JSON object, no other text
"""

def classify_keywords(keywords: list) -> dict:
    must_have = []
    nice_to_have = []
    
    for kw in keywords:
        kw_lower = kw.lower()
        if any(x in kw_lower for x in ["must have", "required", "mandatory"]):
            must_have.append(kw)
        else:
            nice_to_have.append(kw)
            
    return {
        "must_have": must_have,
        "nice_to_have": nice_to_have
    }
    
def compute_keyword_score(text:str, keyword_groups: dict) -> dict:
    score = 0
    used = []
    for kw in keyword_groups["must_have"]:
        if kw.lower() in text.lower():
            score += 3
            used.append(kw)
    for kw in keyword_groups["nice_to_have"]:
        if kw.lower() in text.lower():
            score += 1
            used.append(kw)
                    
    return {
        "score": score,
        "used_keywords": used
    }
                    
async def rewrite_bullets(bullets: list, keywords: list) -> dict:
    if not bullets:
        return {"suggestions": [], "summary": "", "extra_bullets": []}

    sample   = bullets[:5]
    kw_list  = keywords[:20]
    keyword_groups = classify_keywords(kw_list)
    
    user_message = f"""
    BULLETS:
    {json.dumps(sample, indent=2)}

    JD KEYWORDS:
    {json.dumps(kw_list, indent=2)}

    PRIORITY RULES:
    - Must-have keywords are HIGH priority
    - Good-to-have keywords are secondary
    - Each bullet should include at least 1 keyword if natural
    - Do NOT force keywords unnaturally
    Rewrite and return JSON.
    """
    def enrich_scores(data, keyword_groups):
            for item in data.get("suggestions", []):
                score_info = compute_keyword_score(item.get("rewritten", ""), keyword_groups)
                item["keyword_score"] = score_info["score"]
                item["keywords_detected"] = score_info["used_keywords"]
            return data
    try:
        from groq import AsyncGroq
        g = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        resp = await g.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.4,
            max_tokens=1800,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content":user_message}
            ]
        )
        raw = resp.choices[0].message.content.strip()
        data = json.loads(_clean(raw))
        return enrich_scores(data, keyword_groups)

    except Exception as e:
        print(f"[rewriter] Groq failed ({e}), trying Gemini...")
    
    # ── Fallback: Gemini ───────────────────────────────────────
    try:
        import google.generativeai as genai

        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM
        )

        resp = model.generate_content(user_message)
        raw = resp.text.strip()
        data = json.loads(_clean(raw))
        return enrich_scores(data, keyword_groups)
    #we're not catching this error because if both fail, we want to see the raw response to debug why the LLMs are not returning valid JSON     
    except Exception as e:
        print("RAW RESPONSE:", locals().get("raw"))
    raise e

def _clean(s: str) -> str:
    if "```" in s:
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    return s.strip()