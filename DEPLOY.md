# ResumeRadar — Complete Setup & Deployment Guide
# Zero to live public URL, entirely free, no credit card needed.

# ═══════════════════════════════════════════════════════════════
# FREE STACK (verified May 2026)
# ═══════════════════════════════════════════════════════════════
#
#  AI Models:  Groq API    — free forever, no card   (console.groq.com)
#              Gemini API  — free forever, no card   (aistudio.google.com)
#  Backend:    Koyeb       — free forever, no card   (koyeb.com)
#  Frontend:   Vercel      — free forever, no card   (vercel.com)
#  n8n:        Self-hosted via Docker — free forever


# ═══════════════════════════════════════════════════════════════
# STEP 1 — GET FREE API KEYS  (10 minutes)
# ═══════════════════════════════════════════════════════════════

# ── Groq (PRIMARY AI — free) ──────────────────────────
# 1. Go to https://console.groq.com
# 2. Sign up with Google (no card required)
# 3. Click "API Keys" in left sidebar
# 4. Click "Create API Key" → name it "resumeradar"
# 5. COPY the key

# ── Gemini API (BACKUP AI — free) ─────────────────
# 1. Go to https://aistudio.google.com
# 2. Create account (Google login works)
# 3. Settings (top right) → API Keys → Create key
# 4. Copy the key (starts with sk-ant-...)
# 5. You get ~$5 in credits automatically — no card needed


# ═══════════════════════════════════════════════════════════════
# STEP 2 — LOCAL DEVELOPMENT SETUP
# ═══════════════════════════════════════════════════════════════

# ── Backend ───────────────────────────────────────────────────
cd backend

# Create virtual environment
python -m venv venv

# Activate  (Mac/Linux)
source venv/bin/activate
# Activate  (Windows PowerShell)
# venv\Scripts\Activate.ps1
# Activate  (Windows CMD)
# venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt

# Create your .env file (NEVER commit this to Git)
cat > .env << 'EOF'
GROQ_API_KEY=gsk_your_key_here
GEMINI_API_KEY=sk-ant-your_key_here
EOF

# Run the backend
uvicorn main:app --reload --port 8000

# Test it:  open http://localhost:8000
# You should see: {"status":"ok","app":"ResumeRadar","version":"1.0.0"}

# Quick test with curl:
curl -X POST http://localhost:8000/analyze \
  -F "resume_text=Python developer. Skills: Python, Django, REST API, PostgreSQL. Built e-commerce backend." \
  -F "job_description=We need a backend Python developer with Django, REST APIs, Docker, AWS, PostgreSQL."


# ── Frontend ──────────────────────────────────────────────────
# Open a NEW terminal (keep backend running)
cd frontend

# Install Node dependencies
npm install

# Create .env.local  (Vite reads this automatically)
echo "VITE_API_URL=http://localhost:8000" > .env.local

# Run frontend
npm run dev
# Opens at http://localhost:5173  ← open this in browser


# ═══════════════════════════════════════════════════════════════
# STEP 3 — n8n SETUP  (visual agentic workflow, alternative backend)
# ═══════════════════════════════════════════════════════════════

# Install Docker Desktop: https://docker.com/products/docker-desktop
# (Free. Required for n8n.)

# Run n8n locally:
docker run -it --rm \
  --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  -e GROQ_API_KEY=gsk_your_key_here \
  n8nio/n8n

# Open http://localhost:5678
# Create a free local account when prompted.

# Import the workflow:
# 1. Left sidebar → Workflows → click "+" → Import from file
# 2. Select: n8n/resumeradar_workflow.json
# 3. Click "Activate" toggle (top right)

# Your n8n endpoint is now live at:
# POST http://localhost:5678/webhook/analyze-resume

# Test it:
curl -X POST http://localhost:5678/webhook/analyze-resume \
  -H "Content-Type: application/json" \
  -d '{
    "resume_text": "Python developer. Skills: Python, Django, REST API, PostgreSQL.",
    "job_description": "Backend developer needed. Must know Python, Django, Docker, AWS, REST APIs."
  }'

# To use n8n instead of FastAPI, change frontend .env.local:
# VITE_API_URL=http://localhost:5678/webhook/analyze-resume
# Then restart: npm run dev


# ═══════════════════════════════════════════════════════════════
# STEP 4 — PUSH TO GITHUB  (required for deployment)
# ═══════════════════════════════════════════════════════════════

# Create a GitHub account if you don't have one: github.com

# Create a new repository called "resumeradar" on GitHub (public is fine)
# Then push your code:

git init
git add .
git commit -m "feat: initial ResumeRadar — 4-agent ATS resume scanner"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/resumeradar.git
git push -u origin main

# ⚠ IMPORTANT: Create a .gitignore BEFORE pushing:
cat > .gitignore << 'EOF'
.env
.env.local
venv/
__pycache__/
*.pyc
node_modules/
dist/
.DS_Store
EOF
git add .gitignore && git commit -m "chore: add .gitignore"


# ═══════════════════════════════════════════════════════════════
# STEP 5 — DEPLOY BACKEND TO KOYEB  (free forever, no card)
# ═══════════════════════════════════════════════════════════════

# 1. Go to https://koyeb.com  → "Start for free"
# 2. Sign up with GitHub (no credit card needed)
# 3. Click "Create Service" → "Web Service"
# 4. Select "GitHub" deployment → connect your GitHub account
# 5. Choose your "resumeradar" repository
# 6. In "Service settings":
#    - Name: resumeradar-backend
#    - Branch: main
#    - Root directory: backend     ← IMPORTANT (point to backend folder)
#    - Builder: Buildpack
#    - Run command: uvicorn main:app --host 0.0.0.0 --port 8000
#    - Port: 8000
# 7. Scroll to "Environment variables" → Add:
#    GROQ_API_KEY        = gsk_your_key_here
#    GEMINI_API_KEY   = sk-ant-your_key_here
# 8. Choose "Nano" instance (free tier)
# 9. Click "Deploy"
#
# Koyeb will build and deploy. Takes ~3-5 minutes.
# You get a URL like: https://resumeradar-backend-yourname.koyeb.app
#
# Test it: https://your-koyeb-url.koyeb.app/
# Should return: {"status":"ok","app":"ResumeRadar","version":"1.0.0"}


# ═══════════════════════════════════════════════════════════════
# STEP 6 — DEPLOY FRONTEND TO VERCEL  (free forever, no card)
# ═══════════════════════════════════════════════════════════════

# Option A: Vercel CLI (fastest)
npm install -g vercel
cd frontend
vercel

# During setup prompts:
# - Set up and deploy? Y
# - Which scope? your personal account
# - Link to existing project? N
# - Project name? resumeradar
# - Directory? ./  (you're already in frontend/)
# - Override settings? N
# First deploy = preview URL. Then:
vercel --prod   # ← deploys to production

# Option B: Vercel Dashboard (no CLI)
# 1. Go to https://vercel.com → "Start Deploying"
# 2. Sign up with GitHub (free)
# 3. "Add New Project" → Import your "resumeradar" repo
# 4. Configure:
#    - Framework Preset: Vite
#    - Root Directory: frontend    ← IMPORTANT
#    - Build Command: npm run build
#    - Output Directory: dist
# 5. Environment Variables → Add:
#    VITE_API_URL = https://your-koyeb-url.koyeb.app
# 6. Click "Deploy"
#
# You get a URL like: https://resumeradar.vercel.app
# Every time you push to GitHub main → auto-deploys. 

# ── Update CORS in backend ────────────────────────────────────
# In backend/main.py, update line:
#   allow_origins=["*"]
# To:
#   allow_origins=["https://resumeradar.vercel.app"]
# Commit and push → Koyeb auto-redeploys.


# ═══════════════════════════════════════════════════════════════
# STEP 7 — VERIFY EVERYTHING IS WORKING
# ═══════════════════════════════════════════════════════════════

# 1. Open your Vercel URL in browser
# 2. Paste a resume + job description
# 3. Click Analyze
# 4. Should see score, gaps, quick wins, rewrites in ~15 seconds

# If the API call fails:
# - Open browser DevTools → Network tab → look at the /analyze request
# - Check: is VITE_API_URL set correctly in Vercel env vars?
# - Check: is Koyeb service showing "Healthy" status?
# - Check: are GROQ_API_KEY and GEMINI_API_KEY set in Koyeb env vars?


# ═══════════════════════════════════════════════════════════════
# STEP 8 — CUSTOM DOMAIN (optional, free with Freenom or .is-a.dev)
# ═══════════════════════════════════════════════════════════════

# Option 1: .is-a.dev subdomain (free, popular for devs)
# 1. Go to https://is-a.dev  (GitHub-based, free for students)
# 2. Follow instructions to get yourname.is-a.dev
# 3. Point it to your Vercel URL in Vercel Dashboard → Domains

# Option 2: Vercel free subdomain
# Your app is already live at resumeradar.vercel.app — that's enough for a portfolio!


# ═══════════════════════════════════════════════════════════════
# COMPLETE FILE STRUCTURE
# ═══════════════════════════════════════════════════════════════

# resumeradar/
# ├── .gitignore
# ├── DEPLOY.md                    ← this file
# ├── backend/
# │   ├── main.py                  ← FastAPI app, /analyze endpoint
# │   ├── requirements.txt         ← pip dependencies
# │   ├── Procfile                 ← tells Koyeb how to start the app
# │   ├── runtime.txt              ← Python version
# │   ├── .env                     ← YOUR KEYS (never commit!)
# │   ├── agents/
# │   │   ├── __init__.py
# │   │   ├── resume_parser.py     ← Agent 1: extract resume structure
# │   │   ├── jd_parser.py         ← Agent 2: extract JD requirements
# │   │   ├── gap_analyzer.py      ← Agent 3: score + gap analysis
# │   │   └── rewriter.py          ← Agent 4: rewrite bullets
# │   └── utils/
# │       ├── __init__.py
# │       └── pdf_extractor.py     ← PDF/DOCX text extraction
# ├── frontend/
# │   ├── index.html
# │   ├── package.json
# │   ├── vite.config.js
# │   ├── vercel.json              ← Vercel deploy config
# │   ├── .env.local               ← VITE_API_URL (never commit!)
# │   └── src/
# │       ├── main.jsx
# │       ├── index.css            ← global styles, CSS vars
# │       └── App.jsx              ← full UI: score ring, tabs, chips
# └── n8n/
#     └── resumeradar_workflow.json  ← import this into n8n


# ═══════════════════════════════════════════════════════════════
# COST SUMMARY — EVERYTHING FREE
# ═══════════════════════════════════════════════════════════════

# Groq API:      $0 — free tier, very generous limits
# Gemini API:    $0 — free tier, very generous limits
# Koyeb:         $0 — Nano instance, free forever
# Vercel:        $0 — free forever for hobby projects
# n8n:           $0 — self-hosted on your laptop
# GitHub:        $0 — free public repos
# Docker:        $0 — free Docker Desktop
#                                              TOTAL: $0 / month 🎉


# ═══════════════════════════════════════════════════════════════
# WHAT TO PUT ON YOUR RESUME / PORTFOLIO
# ═══════════════════════════════════════════════════════════════

# Project: ResumeRadar — AI-powered ATS Resume Analyzer
# Tech: Python · FastAPI · Groq Llama 3.3 · Gemini API · React · Vite
# Skills demonstrated:
#   - Multi-agent AI architecture (4 specialized AI agents)
#   - Agentic workflow automation (n8n)
#   - REST API development (FastAPI)
#   - Full-stack deployment (Koyeb + Vercel)
#   - Prompt engineering (system prompts for structured JSON output)
#   - PDF parsing (PyMuPDF)
#   - React frontend with animations and data visualization
# Live URL: https://resumeradar.vercel.app
# GitHub: https://github.com/yourname/resumeradar
