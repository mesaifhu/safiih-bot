import os
import json
import time
import random
import logging
import requests
import re

from instagrapi import Client

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("SafiihBot")

# ── Config ────────────────────────────────────────────────────────────────────
IG_USERNAME  = os.environ["IG_USERNAME"]
IG_PASSWORD  = os.environ["IG_PASSWORD"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
THREAD_ID    = os.environ["THREAD_ID"]
BOT_USERNAME = IG_USERNAME.lower()

GH_MODEL    = "meta/Llama-3.3-70B-Instruct"
GH_ENDPOINT = "https://models.github.ai/inference/chat/completions"

POLL_INTERVAL  = 10
MAX_HISTORY    = 6
DATASET_SAMPLE = 200

# ── Load dataset ──────────────────────────────────────────────────────────────
log.info("Loading poetry dataset...")
with open("poetry-dataset.json", encoding="utf-8") as f:
    ALL_SHERS = json.load(f)["DS_UNIFIED"]

POETS = sorted(set(s["poet"] for s in ALL_SHERS))
log.info(f"{len(ALL_SHERS)} shers | {len(POETS)} poets loaded")

# ── Dataset search functions ──────────────────────────────────────────────────
def get_random_sher():
    s = random.choice(ALL_SHERS)
    return f"{s['misra1']}\n{s['misra2']}\n— {s['poet']}"

def get_sher_by_poet(poet_name: str, count: int = 1):
    """Find shers by poet name (fuzzy match)."""
    poet_lower = poet_name.lower()
    matches = [s for s in ALL_SHERS if poet_lower in s["poet"].lower()]
    if not matches:
        return None
    selected = random.sample(matches, min(count, len(matches)))
    return "\n\n".join(f"{s['misra1']}\n{s['misra2']}\n— {s['poet']}" for s in selected)

def search_shers_by_keyword(keyword: str, count: int = 2):
    """Search shers containing a keyword in either misra."""
    kw = keyword.lower()
    matches = [
        s for s in ALL_SHERS
        if kw in s.get("misra1", "").lower() or kw in s.get("misra2", "").lower()
    ]
    if not matches:
        return None
    selected = random.sample(matches, min(count, len(matches)))
    return "\n\n".join(f"{s['misra1']}\n{s['misra2']}\n— {s['poet']}" for s in selected)

def detect_poet_request(text: str):
    """Check if user is asking for a sher by a specific poet."""
    text_lower = text.lower()
    for poet in POETS:
        if poet.lower() in text_lower:
            return poet
    return None

def detect_random_request(text: str):
    """Check if user wants a random sher."""
    triggers = ["random", "koi sher", "کوئی شعر", "sher sunao", "share a sher", 
                "any sher", "ek sher", "ایک شعر", "sher suno", "poem", "verse"]
    text_lower = text.lower()
    return any(t in text_lower for t in triggers)

def get_dataset_context(user_message: str):
    """
    Try to fulfill request directly from dataset.
    Returns (direct_reply, context_shers) tuple.
    direct_reply = a ready string to send if we can answer directly
    context_shers = relevant shers to add to AI prompt for context
    """
    # Check for poet-specific request
    poet = detect_poet_request(user_message)
    if poet:
        shers = get_sher_by_poet(poet, count=2)
        if shers:
            log.info(f"Fetched shers for poet: {poet}")
            return shers, shers

    # Check for random sher request
    if detect_random_request(user_message):
        sher = get_random_sher()
        log.info("Fetched random sher from dataset")
        return sher, sher

    # Otherwise just provide sample context for AI
    sample = random.sample(ALL_SHERS, min(DATASET_SAMPLE, len(ALL_SHERS)))
    context = "\n".join(f"[{s['poet']}] {s['misra1']} | {s['misra2']}" for s in sample)
    return None, context

# ── GitHub Models API ─────────────────────────────────────────────────────────
def call_github_model(messages):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    body = {
        "model": GH_MODEL,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 300,
        "stream": False
    }
    resp = requests.post(GH_ENDPOINT, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

# ── System prompt ─────────────────────────────────────────────────────────────
def system_prompt(context_shers: str):
    return f"""You are Safiih, an Urdu poetry companion bot in an Instagram group.

RULES:
- Speak ONLY in English
- Keep replies short: 3-5 sentences max (unless explaining a sher)
- Only discuss Urdu poetry topics
- When sharing a sher always mention the poet
- Be warm, passionate about poetry, and invite discussion
- If shers are provided in DATASET CONTEXT, use them in your reply

POETS IN YOUR DATASET: {", ".join(POETS)}

DATASET CONTEXT (real shers from the dataset):
{context_shers}"""

# ── Conversation memory ───────────────────────────────────────────────────────
memory = {}

def ai_reply(user_id: str, text: str) -> str:
    hist = memory.setdefault(user_id, [])

    # Try to get direct answer or context from dataset
    direct_reply, context_shers = get_dataset_context(text)

    # If we have a direct reply (poet/random request), send it straight away
    # but still run it through AI to add a nice intro line
    if direct_reply:
        prompt = f"The user asked: '{text}'\nHere are real shers from the dataset to share:\n{direct_reply}\nPresent these shers naturally with a warm one-line intro. Keep it brief."
        hist.append({"role": "user", "content": prompt})
    else:
        hist.append({"role": "user", "content": text})

    if len(hist) > MAX_HISTORY * 2:
        memory[user_id] = hist[-(MAX_HISTORY * 2):]

    try:
        messages = [{"role": "system", "content": system_prompt(context_shers)}, *memory[user_id]]
        reply = call_github_model(messages)
        memory[user_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        log.error(f"AI error: {e}")
        return "I'm lost in a ghazal for a moment — please try again. 🌹"

# ── Instagram ─────────────────────────────────────────────────────────────────
ig = Client()

def login():
    log.info("Logging in to Instagram...")
    ig.login(IG_USERNAME, IG_PASSWORD)
    log.info("Logged in ✅")

def fetch_messages(limit=10):
    try:
        return ig.direct_thread(THREAD_ID, amount=limit).messages
    except Exception as e:
        log.error(f"Fetch error: {e}")
        return []

def send(text: str):
    try:
        ig.direct_send(text, thread_ids=[THREAD_ID])
        log.info(f"Sent: {text[:70]}")
    except Exception as e:
        log.error(f"Send error: {e}")

def mentioned(text: str) -> bool:
    return bool(text) and f"@{BOT_USERNAME}" in text.lower()

def strip_mention(text: str) -> str:
    return text.lower().replace(f"@{BOT_USERNAME}", "").strip() or "share a random sher"

# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    login()
    log.info(f"Watching thread {THREAD_ID} | Trigger: @{BOT_USERNAME}")

    seen = set()
    for m in fetch_messages(20):
        seen.add(m.id)
    log.info(f"Seeded {len(seen)} existing messages")

    while True:
        try:
            for msg in reversed(fetch_messages(10)):
                if msg.id in seen:
                    continue
                seen.add(msg.id)

                if msg.item_type != "text":
                    continue

                text = msg.text or ""
                uid  = str(msg.user_id)
                log.info(f"[{uid}] {text[:80]}")

                if mentioned(text):
                    log.info("Mentioned — generating reply...")
                    reply = ai_reply(uid, strip_mention(text))
                    time.sleep(2)
                    send(reply)

        except Exception as e:
            log.error(f"Loop error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run()
