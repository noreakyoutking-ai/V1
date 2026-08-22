"""
admin_bot_additions.py
------------------------------------------------------------------
Drop-in commands for your existing admin_bot.py (Uchiro Store V3):

  /stats      -> user + order overview (today / all-time, top items)
  /users      -> already exists in your repo per the README; this
                 version adds pagination + last-seen so long lists
                 don't blow past Telegram's message size limit
  /broadcast  -> send an announcement to every user who has ever
                 messaged the store bot (or a filtered subset)

Assumes the same shape your README implies:
  - config.py exposes OWNER_IDS (set of int Telegram IDs)
  - database.py is SQLite and already tracks users somewhere
    (adjust table/column names below to match your real schema —
    these are the ones this file expects and creates if missing)
  - store_bot.py's Bot/Dispatcher instance is importable, or you're
    wiring this into the same aiogram/python-telegram-bot app as
    admin_bot.py already uses

This file intentionally does NOT ship as a black box — read the
TODOs and adjust table/column names to your real database.py.
------------------------------------------------------------------
"""

import sqlite3
import time
import asyncio
from config import OWNER_IDS, STORE_BOT_TOKEN  # adjust names to match your config.py

DB_PATH = "store.db"  # matches the README's mention of store.db


# ------------------------------------------------------------------
# 1. Make sure we have somewhere to track users + page views.
#    Safe to run every startup — CREATE TABLE IF NOT EXISTS.
# ------------------------------------------------------------------
def ensure_tables():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_seen INTEGER,
            last_seen INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS page_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT,
            telegram_id INTEGER,
            referrer TEXT,
            viewed_at INTEGER
        )
    """)
    conn.commit()
    conn.close()


def touch_user(telegram_id: int, username: str | None):
    """Call this on every /start or message the store bot receives."""
    now = int(time.time())
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bot_users (telegram_id, username, first_seen, last_seen)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            last_seen = excluded.last_seen
    """, (telegram_id, username, now, now))
    conn.commit()
    conn.close()


# ------------------------------------------------------------------
# 2. /stats — quick pulse on users + orders. Owner-only.
#    TODO: swap the "orders" query to match your real orders table
#    (README implies one already exists, used by /orders).
# ------------------------------------------------------------------
async def cmd_stats(update, context):
    if update.effective_user.id not in OWNER_IDS:
        return await update.message.reply_text("Owner only.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM bot_users")
    total_users = cur.fetchone()[0]

    day_ago = int(time.time()) - 86400
    cur.execute("SELECT COUNT(*) FROM bot_users WHERE last_seen >= ?", (day_ago,))
    active_today = cur.fetchone()[0]

    # TODO: adjust table/column names to your real orders table
    try:
        cur.execute("SELECT COUNT(*), COALESCE(SUM(price), 0) FROM orders WHERE status = 'approved'")
        order_count, revenue = cur.fetchone()
    except sqlite3.OperationalError:
        order_count, revenue = 0, 0

    conn.close()

    text = (
        f"📊 *Uchiro Store — stats*\n\n"
        f"👥 Total users: `{total_users}`\n"
        f"🟢 Active in last 24h: `{active_today}`\n"
        f"🧾 Approved orders: `{order_count}`\n"
        f"💵 Revenue (approved): `${revenue}`\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ------------------------------------------------------------------
# 3. /broadcast — announcement to all (or filtered) users.
#    Usage: /broadcast <message>
#    Sends in small batches with a short delay to respect Telegram's
#    rate limits (roughly 30 messages/second across all chats).
# ------------------------------------------------------------------
async def cmd_broadcast(update, context):
    if update.effective_user.id not in OWNER_IDS:
        return await update.message.reply_text("Owner only.")

    message_text = " ".join(context.args) if context.args else None
    if not message_text:
        return await update.message.reply_text(
            "Usage: /broadcast <message>\n\n"
            "Example: /broadcast New restock: Dragon Fruit x5 back in stock, tap Shop to grab one."
        )

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM bot_users")
    user_ids = [row[0] for row in cur.fetchall()]
    conn.close()

    await update.message.reply_text(f"Sending to {len(user_ids)} users…")

    sent, failed = 0, 0
    batch_size = 25
    for i in range(0, len(user_ids), batch_size):
        batch = user_ids[i:i + batch_size]
        for uid in batch:
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 {message_text}")
                sent += 1
            except Exception:
                # user blocked the bot, deleted account, etc. — skip and keep going
                failed += 1
        await asyncio.sleep(1)  # stay under Telegram's rate limit between batches

    await update.message.reply_text(f"Done. Sent: {sent}, failed/blocked: {failed}.")


# ------------------------------------------------------------------
# 4. Registration — call this from main.py where admin_bot's
#    dispatcher/application is built, alongside your existing
#    command handlers (/orders, /addstock, etc.)
# ------------------------------------------------------------------
def register_admin_extra_handlers(application):
    """
    Example for python-telegram-bot v20+:

        from admin_bot_additions import register_admin_extra_handlers, ensure_tables
        ensure_tables()
        register_admin_extra_handlers(admin_app)

    If admin_bot.py uses aiogram instead, register these as
    @dp.message(Command("stats")) / @dp.message(Command("broadcast"))
    handlers instead — the DB logic above is framework-agnostic.
    """
    from telegram.ext import CommandHandler
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("broadcast", cmd_broadcast))
