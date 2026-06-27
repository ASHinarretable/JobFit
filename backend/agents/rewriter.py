"""
agents/rewriter.py  —  AGENT 4
Rewrites weak resume bullets to include JD keywords naturally.
Uses Gemini Flash first (free, high quality), falls back to Groq automatically.
"""
import json, os, re, asyncio
from collections import Counter
from dotenv import load_dotenv
from utils.json_utils import extract_json
from utils.retry import retry_async
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
# ════════════════════════════════════════════════════════════
# UTIL: TEXT NORMALIZATION
# ════════════════════════════════════════════════════════════
def normalize(text: str):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.split()

# ════════════════════════════════════════════════════════════
# IMPROVED KEYWORD CLASSIFICATION
# ════════════════════════════════════════════════════════════
def classify_keywords(keywords: list) -> dict:
    """
    Heuristic:
    - Keywords appearing more frequently → must-have
    """
    priority_score = {}
    explicit_markers = ["must have", "required", "mandatory"]
    for kw in keywords:
        kw_lower = kw.lower()

        score = 0

        if any(marker in kw_lower for marker in explicit_markers):
            score += 3
        freq = Counter(keywords)
        score += freq[kw]  # frequency boost

        clean_kw = kw_lower
        for marker in explicit_markers:
            clean_kw = clean_kw.replace(marker, "").strip(" :-")

        priority_score[clean_kw] = priority_score.get(clean_kw, 0) + score

    must_have = [k for k, v in priority_score.items() if v >= 3]
    nice_to_have = [k for k, v in priority_score.items() if v < 3]
            
    return {
        "must_have": list(must_have),
        "nice_to_have": list(nice_to_have)
    }

# ════════════════════════════════════════════════════════════
# IMPROVED SCORING
# ════════════════════════════════════════════════════════════   
def keyword_match_score(text: str, keywords: list):
    tokens = normalize(text)
    token_str = " ".join(tokens)
    matched = []
    
    for kw in keywords:
        kw_norm = " ".join(normalize(kw))
        
        if kw_norm in token_str:
            matched.append(kw)
    return matched
         
def compute_keyword_score(text:str, keyword_groups: dict) -> dict:

    used = []
    
    must = keyword_match_score(text, keyword_groups["must_have"])
    nice = keyword_match_score(text, keyword_groups["nice_to_have"])
    used.extend(must)
    used.extend(nice)
    
    score = len(must) * 3 + len(nice) * 1
                        
    return {
        "score": score,
        "used_keywords": used
    }

# ════════════════════════════════════════════════════════════
# HALLUCINATION GUARD
# ════════════════════════════════════════════════════════════
def validate_output(data, original_bullets):
    original_text = " ".join(original_bullets).lower()
    for item in data.get("suggestions", []):
        rewritten = item.get("rewritten", "").lower()
        
        #avoid unrelated content
        if len(rewritten) > 0 and not any( word in original_text for word in rewritten.split()[:3]):
            item["warning"] = "Possibly hallucinating content detected"
    return data
 
# ════════════════════════════════════════════════════════════
# RETRY WRAPPER
# ════════════════════════════════════════════════════════════
async def retry_call(fn, retries=3, delay=1):
    last_error = None
    for i in range(retries):
        try:
            return await fn()
        except Exception as e:
            last_error = e
            await asyncio.sleep(delay * (2 ** i))
    raise last_error
 
# ════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ════════════════════════════════════════════════════════════                        
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
    def enrich(data, keyword_groups):
            for item in data.get("suggestions", []):
                score_info = compute_keyword_score(item.get("rewritten", ""), keyword_groups)
                item["keyword_score"] = score_info["score"]
                item["keywords_detected"] = score_info["used_keywords"]
            return data
    # ───────── GROQ ─────────
    async def call_groq():
        from groq import AsyncGroq

        g = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

        resp = await g.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.4,
            max_tokens=1800,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_message}
            ]
        )

        raw = resp.choices[0].message.content
        return extract_json(raw)

    try:
        data = await retry_call(call_groq)
        return validate_output(enrich(data, keyword_groups), bullets)

    except Exception as groq_error:
        print(f"[rewriter] Groq failed: {groq_error}")

    # ───────── GEMINI FALLBACK ─────────
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError("Gemini SDK not installed")

    async def call_gemini():
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM
        )

        resp = model.generate_content(user_message)
        return extract_json(resp.text)

    try:
        data = await retry_call(call_gemini)
        return validate_output(enrich(data, keyword_groups), bullets)

    except Exception as gemini_error:
        raise RuntimeError(
            f"Both Groq and Gemini failed.\nGroq: {groq_error}\nGemini: {gemini_error}"
        )