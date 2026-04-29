import os
import json
import time
import random
import logging
from openai import OpenAI
from instagrapi import Client

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("SafiihBot")

# ── Config (from Railway environment variables) ───────────────────────────────
IG_USERNAME  = os.environ["IG_USERNAME"]
IG_PASSWORD  = os.environ["IG_PASSWORD"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
THREAD_ID    = os.environ["THREAD_ID"]
BOT_USERNAME = IG_USERNAME.lower()

POLL_INTERVAL    = 10   # seconds between checks
MAX_HISTORY      = 6    # conversation turns kept per user
DATASET_SAMPLE   = 250  # shers sent to AI per request (token budget)

# ── Load dataset ──────────────────────────────────────────────────────────────
log.info("Loading poetry dataset...")
with open("poetry-dataset.json", encoding="utf-8") as f:
    ALL_SHERS = json.load(f)["DS_UNIFIED"]

POETS = sorted(set(s["poet"] for s in ALL_SHERS))
log.info(f"{len(ALL_SHERS)} shers | {len(POETS)} poets loaded")

def sample_shers(n=DATASET_SAMPLE):
    sample = random.sample(ALL_SHERS, min(n, len(ALL_SHERS)))
    return "\n".join(f"[{s['poet']}] {s['misra1']} | {s['misra2']}" for s in sample)

# ── AI client (GitHub Models) ─────────────────────────────────────────────────
ai = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=GITHUB_TOKEN,
)

SYSTEM_PROMPT_TEMPLATE = """You are Safiih, an Urdu poetry companion bot in an Instagram group.

RULES:
- Speak ONLY in English
- Keep replies short: 3-5 sentences max (unless explaining a sher)
- Only discuss Urdu poetry topics
- When sharing a sher always mention the poet
- Be warm, passionate about poetry, and invite discussion

POETS IN YOUR DATASET: {poets}

SAMPLE SHERS (format: [Poet] misra1 | misra2):
{shers}"""

def system_prompt():
    return SYSTEM_PROMPT_TEMPLATE.format(
        poets=", ".join(POETS),
        shers=sample_shers()
    )

# ── Conversation memory ───────────────────────────────────────────────────────
memory = {}  # { user_id: [ {role, content}, ... ] }

def ai_reply(user_id: str, text: str) -> str:
    hist = memory.setdefault(user_id, [])
    hist.append({"role": "user", "content": text})

    # Trim old turns to save tokens
    if len(hist) > MAX_HISTORY * 2:
        memory[user_id] = hist[-(MAX_HISTORY * 2):]

    try:
        resp = ai.chat.completions.create(
            model="meta-llama-3.3-70b-instruct",
            messages=[{"role": "system", "content": system_prompt()}, *memory[user_id]],
            max_tokens=280,
            temperature=0.75,
        )
        reply = resp.choices[0].message.content.strip()
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
    return text.lower().replace(f"@{BOT_USERNAME}", "").strip() or "Share a sher with me"

# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    login()
    log.info(f"Watching thread {THREAD_ID} | Trigger: @{BOT_USERNAME}")

    seen = set()

    # Seed existing messages so bot doesn't reply to old chat on startup
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
