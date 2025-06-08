import os, random, io, asyncio, html, requests, datetime as dt
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot, InputFile
from zoneinfo import ZoneInfo
import os

# ─── CONFIG ──────────────────────────────────────────────────────────────────────
BOT_TOKEN  = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

FONT_PATH = os.path.join(os.path.dirname(__file__), "ARLRDBD.TTF")
KYIV       = ZoneInfo("Europe/Kyiv")
MIN_AMOUNT = 200
MAX_AMOUNT = 1500

bot = Bot(BOT_TOKEN)

# ─── DATA HELPERS ────────────────────────────────────────────────────────────────
def load_groups_from_file(path="teams.txt"):
    groups = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if ':' in line:
                    name, team = line.strip().split(':', 1)
                    groups[name.strip()] = team.strip()
    except Exception as e:
        print("Failed to load team groups:", e)
    return groups

GROUPS = load_groups_from_file()

def load_person():
    nick = random.choice(list(GROUPS))
    return nick, GROUPS[nick]

def fetch_tx():
    url = "https://apilist.tronscan.org/api/token_trc20/transfers"
    p   = {"limit":100, "start":0, "sort":"-timestamp",
           "contract_address":"TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"}
    try:
        resp = requests.get(url, params=p, timeout=10).json()
        for tx in resp.get("token_transfers", []):
            amount = int(tx["quant"]) / 10**int(tx["tokenInfo"]["tokenDecimal"])
            if amount.is_integer() and MIN_AMOUNT <= amount <= MAX_AMOUNT:
                return int(amount), tx["transaction_id"]
    except Exception:
        pass
    return random.randint(MIN_AMOUNT, MAX_AMOUNT), "".join(random.choices("abcdef0123456789", k=64))

# ─── IMAGE GENERATION (unchanged) ────────────────────────────────────────────────
def make_image(amount: int, w: int = 1024, h: int = 512) -> io.BytesIO:
    try:
        img = Image.new("RGB", (w, h), (10, 15, 20))
        d   = ImageDraw.Draw(img)

        for _ in range(15):
            d.line([(random.randint(0, w), random.randint(0, h)),
                    (random.randint(0, w), random.randint(0, h))],
                   fill=(0, random.randint(80, 120), 0), width=1)

        small_font = ImageFont.truetype(FONT_PATH, 12) if os.path.exists(FONT_PATH) else ImageFont.load_default()
        for _ in range(300):
            d.text((random.randint(0, w), random.randint(0, h)), random.choice("01"),
                   font=small_font, fill=(0, random.randint(50, 100), 0))

        for r in range(50, 0, -5):
            d.ellipse([(w // 2 - r, h // 2 - r), (w // 2 + r, h // 2 + r)],
                      outline=(0, random.randint(100, 150), 0), width=1)

        big_font = ImageFont.truetype(FONT_PATH, 220) if os.path.exists(FONT_PATH) else ImageFont.load_default()
        label    = f"+{amount}$"
        try:
            x1, y1, x2, y2 = d.textbbox((0, 0), label, font=big_font)
            text_w, text_h = x2 - x1, y2 - y1
        except AttributeError:
            text_w, text_h = d.textsize(label, font=big_font)

        x, y = (w - text_w) / 2, (h - text_h) / 2 - 20

        for offset in range(20, 0, -2):
            d.text((x, y), label, font=big_font, fill=(0, 25 + offset * 6, 0))
        for dx, dy in [(-2, -2), (2, 2), (-1, 1), (1, -1)]:
            d.text((x + dx, y + dy), label, font=big_font, fill=(0, 80, 0))
        d.text((x, y), label, font=big_font, fill=(0, 255, 120))

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for yy in range(0, h, 3):
            od.line([(0, yy), (w, yy)], fill=(0, 10, 0, 30), width=1)
        img.paste(overlay, (0, 0), overlay)

    except Exception as err:
        print("⚠️  make_image() fallback:", err)
        img = Image.new("RGB", (w, h), "black")
        d   = ImageDraw.Draw(img)
        fallback_font = ImageFont.load_default()
        msg = f"+{amount}$"
        tw, th = d.textsize(msg, font=fallback_font)
        d.text(((w - tw) / 2, (h - th) / 2), msg, fill="white", font=fallback_font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ─── TELEGRAM POST ───────────────────────────────────────────────────────────────
async def send_post():
    try:
        nick, lead = load_person()
        amt, txid  = fetch_tx()
        worker     = round(amt * 0.45, 2)
        img        = make_image(amt)

        cap = (
            "❗️ <b>Успешный залив</b> ❗️\n"
            f"👤 <b>Никнейм:</b> {html.escape(nick,  quote=False)}\n"
            f"👥 <b>Тимлидер:</b> {html.escape(lead, quote=False)}\n"
            f"🤑 <b>Сумма залива:</b> {amt}$\n"
            f"💲 <b>Часть воркера:</b> {worker}$\n"
            f"🔗 <b>Транзакция:</b> "
            f"<a href=\"https://tronscan.org/#/transaction/{txid}\">TxID</a>"
        )

        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=InputFile(img, "tx.png"),
            caption=cap,
            parse_mode="HTML"
        )

    except Exception:
        import traceback
        print("Send error → full traceback follows:")
        traceback.print_exc()

# ─── SCHEDULER ───────────────────────────────────────────────────────────────────
def todays_window(now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """Return randomized start & end datetimes for *today* in Kyiv TZ."""
    start_offset_min = random.randint(0, 60)          # 10:00-11:00
    end_offset_min   = random.randint(0, 1)         # 19:00-21:00
    start = now.replace(hour=10,  minute=0, second=0, microsecond=0) + dt.timedelta(minutes=start_offset_min)
    end   = now.replace(hour=20, minute=0, second=0, microsecond=0) + dt.timedelta(minutes=end_offset_min)
    return start, end

async def sleep_until(moment: dt.datetime):
    now = dt.datetime.now(KYIV)
    seconds = (moment - now).total_seconds()
    if seconds > 0:
        await asyncio.sleep(seconds)

# ─── MAIN LOOP ───────────────────────────────────────────────────────────────────
async def weekday_runner():
    while True:
        now = dt.datetime.now(KYIV)

        # If weekend, sleep until next Monday 10:00
        if now.weekday() >= 5:                      # 5 = Saturday, 6 = Sunday
            days_ahead = 7 - now.weekday()          # days to Monday
            next_monday = (now + dt.timedelta(days=days_ahead)).replace(
                hour=10, minute=0, second=0, microsecond=0)
            await sleep_until(next_monday)
            continue

        # Generate today's random window
        start_dt, end_dt = todays_window(now)

        # If we haven’t reached the start → wait
        if now < start_dt:
            await sleep_until(start_dt)

        # Active posting period
        while dt.datetime.now(KYIV) < end_dt:
            await send_post()
            wait_minutes = random.randint(1, 78)
            await asyncio.sleep(wait_minutes * 60)

        # After end time, sleep until tomorrow 10:00
        tomorrow = (dt.datetime.now(KYIV) + dt.timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0)
        await sleep_until(tomorrow)

if __name__ == "__main__":
    asyncio.run(weekday_runner())
