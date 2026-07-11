# Deploying to Render

This guide gets you from a local working app to a public URL your hackathon team can use.

## 0. Push your code to GitHub

Render deploys from a Git repo. Push this folder to a new GitHub repo:

1. Create a new empty repo at https://github.com/new (e.g. `chat-with-video`)
   - **Do not** initialize with README, .gitignore, or license (we have them)
2. From this folder:
   ```bash
   git init                       # only if not already a git repo
   git add .
   git commit -m "Initial deploy"
   git branch -M main
   git remote add origin https://github.com/<your-username>/chat-with-video.git
   git push -u origin main
   ```

## 1. Sign up on Render

Go to https://render.com and sign up with your GitHub account (easiest).

## 2. Create a new Web Service

1. Click **"New +"** → **"Web Service"**
2. Connect your GitHub repo (`chat-with-video`)
3. Render auto-detects `render.yaml`. If it asks, pick **"Apply YAML"** or fill in manually:

| Setting | Value |
|---|---|
| **Name** | `chat-with-video` (or anything) |
| **Runtime** | Python 3 |
| **Build Command** | `pip install --upgrade pip && pip install -r requirements.txt` |
| **Start Command** | `uvicorn app:app --host 0.0.0.0 --port $PORT` |
| **Plan** | Free |

4. Click **"Advanced"** and add these environment variables:

   | Key | Value |
   |---|---|
   | `GEMINI_API_KEY` | your Gemini API key |
   | `GROQ_API_KEY` | your Groq API key |
   | `DATABASE_URL` | your Neon connection string |

   (Find these in your local `.env` file — copy them, don't share the file.)

5. Click **"Create Web Service"**.

## 3. Wait for the deploy to finish

First deploy takes 2-4 minutes. You'll see logs streaming in the Render dashboard.
When it says **"Live"**, your public URL is at the top, e.g.
`https://chat-with-video.onrender.com`.

## 4. Test it

1. Open the URL in a browser.
2. You should see 5 Bangla ML lesson cards.
3. Click one, chat, verify the jump-to-timestamp links work.

## What happens if Render spins down?

The free plan sleeps after 15 min of no traffic. The **first** request after
that takes ~30s ("spinning up..."). Subsequent requests are fast. For a
hackathon demo this is fine.

## Limitations to know about

- **No ffmpeg on Render**, so `yt-dlp` audio extraction (used for Whisper ASR)
  will fail on Render for NEW videos. The 5 videos already in your Neon DB
  will work perfectly. To add new videos, run `python pipeline.py <id>` on
  your local machine first — that stores the transcript in Neon, then
  Render just reads it.
- **Gemini free tier** has a per-minute quota. If you hit it, the chat will
  auto-fall back to Groq. Groq is also free, so the demo keeps working.