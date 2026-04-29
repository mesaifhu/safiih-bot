# Safiih Instagram Poetry Bot

A bot that monitors an Instagram group and replies with Urdu poetry knowledge when @mentioned.

## Setup Guide

### Step 1 — Get the Thread ID

The THREAD_ID is needed for the bot to know which group to watch.

1. Open Instagram on PC (instagram.com)
2. Go to the group chat
3. Look at the URL: `https://www.instagram.com/direct/t/XXXXXXXXXX/`
4. The number after `/t/` is your Thread ID

### Step 2 — Create GitHub Repository

1. Go to github.com → New repository
2. Name it `safiih-bot`
3. Upload these files:
   - `bot.py`
   - `requirements.txt`
   - `Procfile`
   - `poetry-dataset.json`

### Step 3 — Deploy on Railway

1. Go to railway.app → Sign up with GitHub
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `safiih-bot` repo
4. Go to **Variables** tab and add:

```
IG_USERNAME   = safiihbot
IG_PASSWORD   = your_password
GITHUB_TOKEN  = your_github_models_token
THREAD_ID     = your_thread_id_from_step1
```

5. Railway will auto-deploy and start the bot

### Step 4 — Check Logs

- In Railway dashboard → click your deployment → **View Logs**
- You should see:
  ```
  Loaded 3532 shers | 38 poets
  Logged in ✅
  Watching thread XXXXX | Trigger: @safiihbot
  ```

## Usage

In the Instagram group, members just type:
```
@safiihbot tell me a sher by Ghalib
@safiihbot explain the meaning of ghazal
@safiihbot who is Faiz Ahmed Faiz?
```

The bot will only reply when @mentioned.

## Notes

- Bot checks for new messages every 10 seconds
- Responds only to text messages with @safiihbot mention
- Speaks only in English
- Uses GitHub Models (Llama 3.3 70B) — same as Safiih web app
