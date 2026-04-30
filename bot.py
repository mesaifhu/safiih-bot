import json
import time
import random
import logging
import requests

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("SafiihBot")

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN    = "8779033281:AAHYmLn2J7yUCQEijuVe9ursWD3cwa59eks"
GROUP_ID     = "-1003787941813"
GITHUB_TOKEN = "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"
BOT_USERNAME = "safiihpoetry_bot"

GH_MODEL     = "meta/Llama-3.3-70B-Instruct"
GH_ENDPOINT  = "https://models.github.ai/inference/chat/completions"
TG_API       = f"https://api.telegram.org/bot{BOT_TOKEN}"

DATASET_SAMPLE = 200
MAX_HISTORY    = 6

# ── Load dataset ──────────────────────────────────────────────────────────────
log.info("Loading poetry dataset...")
with open("poetry-dataset.json", encoding="utf-8") as f:
    ALL_SHERS = json.load(f)["DS_UNIFIED"]

POETS = sorted(set(s["poet"] for s in ALL_SHERS))
log.info(f"{len(ALL_SHERS)} shers | {len(POETS)} poets loaded")

# ── Dataset functions ─────────────────────────────────────────────────────────
def get_random_sher():
    s = random.choice(ALL_SHERS)
    return f"{s['misra1']}\n{s['misra2']}\n\n— {s['poet']}"

def get_sher_by_poet(poet_name: str):
    matches = [s for s in ALL_SHERS if poet_name.lower() in s["poet"].lower()]
    if not matches:
        return None
    s = random.choice(matches)
    return f"{s['misra1']}\n{s['misra2']}\n\n— {s['poet']}"

def detect_poet(text: str):
    for poet in POETS:
        if poet.lower() in text.lower():
            return poet
    return None

def is_random_request(text: str):
    triggers = ["random", "koi sher", "sher sunao", "share a sher",
                "any sher", "ek sher", "sher suno", "poem", "verse",
                "کوئی شعر", "ایک شعر", "شعر سناؤ"]
    return any(t in text.lower() for t in triggers)

def get_context(text: str):
    poet = detect_poet(text)
    if poet:
        shers = get_sher_by_poet(poet)
        return shers, shers
    if is_random_request(text):
        sher = get_random_sher()
        return sher, sher
    sample = random.sample(ALL_SHERS, min(DATASET_SAMPLE, len(ALL_SHERS)))
    context = "\n".join(f"[{s['poet']}] {s['misra1']} | {s['misra2']}" for s in sample)
    return None, context

# ── GitHub Models AI ──────────────────────────────────────────────────────────
def call_ai(messages):
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

def system_prompt(context):
    return f"""You are Safiih, an Urdu poetry companion bot in a Telegram group.

RULES:
- Speak ONLY in English
- Keep replies short: 3-5 sentences max (unless explaining a sher)
- Only discuss Urdu poetry topics
- When sharing a sher always mention the poet
- Be warm, passionate about poetry, and invite discussion
- If shers are provided in DATASET CONTEXT, use them in your reply

POETS IN YOUR DATASET: {", ".join(POETS)}

DATASET CONTEXT:
{context}"""

# ── Conversation memory ───────────────────────────────────────────────────────
memory = {}

def ai_reply(user_id: str, text: str) -> str:
    hist = memory.setdefault(user_id, [])
    direct, context = get_context(text)

    if direct:
        prompt = f"User asked: '{text}'\nShare these shers naturally with a warm one-line intro:\n{direct}"
        hist.append({"role": "user", "content": prompt})
    else:
        hist.append({"role": "user", "content": text})

    if len(hist) > MAX_HISTORY * 2:
        memory[user_id] = hist[-(MAX_HISTORY * 2):]

    try:
        msgs = [{"role": "system", "content": system_prompt(context)}, *memory[user_id]]
        reply = call_ai(msgs)
        memory[user_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        log.error(f"AI error: {e}")
        return "I'm lost in a ghazal for a moment — please try again. 🌹"

# ── Telegram API functions ────────────────────────────────────────────────────
def get_updates(offset=None):
    params = {"timeout": 30, "offset": offset}
    try:
        resp = requests.get(f"{TG_API}/getUpdates", params=params, timeout=35)
        return resp.json().get("result", [])
    except Exception as e:
        log.error(f"getUpdates error: {e}")
        return []

def send_message(chat_id, text, reply_to=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    try:
        requests.post(f"{TG_API}/sendMessage", data=data, timeout=15)
        log.info(f"Sent: {text[:60]}")
    except Exception as e:
        log.error(f"Send error: {e}")

# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    log.info(f"Safiih Telegram Bot started! @{BOT_USERNAME}")
    log.info(f"Watching group: {GROUP_ID}")
    offset = None

    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            user_id = str(msg.get("from", {}).get("id", ""))
            msg_id  = msg.get("message_id")

            # Only respond in the group
            if chat_id != GROUP_ID:
                continue

            # Only respond when @mentioned
            if f"@{BOT_USERNAME}" not in text.lower():
                continue

            clean = text.lower().replace(f"@{BOT_USERNAME}", "").strip()
            if not clean:
                clean = "share a random sher"

            log.info(f"Mentioned by {user_id}: {clean[:80]}")
            reply = ai_reply(user_id, clean)
            send_message(GROUP_ID, reply, reply_to=msg_id)

        time.sleep(1)

if __name__ == "__main__":
    run()
