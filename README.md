# GenAI Sales Analytics Engine

A recruiter-ready full-stack version of the notebook-based GenAI Analytics Engine.

## Architecture

```text
Excel upload + natural-language question
                |
                v
        TypeScript / React UI
                |
                v
          FastAPI backend
                |
       +--------+---------+
       |                  |
       v                  v
  GPT intent parser   Pandas compute engine
       |                  |
       +--------+---------+
                |
                v
       Generated explanation
                |
                v
       Answer + table + chart
```

The LLM interprets the question and creates a structured intent. Pandas performs the actual numerical computation deterministically.

## 1. Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env`:

```env
OPENAI_API_KEY=YOUR_NEW_API_KEY
MODEL=gpt-5-nano
```

Then:

```bash
uvicorn main:app --reload --port 8000
```

Health check:

```text
http://localhost:8000/health
```

## 2. Run the TypeScript frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal, normally:

```text
http://localhost:5173
```

If the backend is hosted somewhere else, create:

```env
VITE_API_URL=https://YOUR-BACKEND-DOMAIN/api/analyze
```

and rebuild:

```bash
npm run build
```

## 3. Deploy

GitHub Pages can host the TypeScript/React frontend after it is built.

The FastAPI backend must be deployed separately to a backend-capable host. Do NOT put the OpenAI API key in the GitHub Pages frontend.

For production, replace `allow_origins=["*"]` in `backend/main.py` with your actual frontend domain.

## Security

The original notebook contained an OpenAI API key. That key should be revoked/rotated immediately and must not be committed to GitHub.

Use `.env` or your hosting provider's secret/environment-variable system instead.
