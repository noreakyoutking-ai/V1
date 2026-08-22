import os
import logging
import sqlite3
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

import database as db
from config import (ADMIN_BOT_TOKEN, STORE_BOT_TOKEN, 
                    CATEGORIES, CURRENCY, CREATOR_NAME, CREATOR_YOUTUBE)
from utils import (format_price, save_telegram_photo, warranty_status, 
                    get_totp_code)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "store.db"

# ---------------------------------------------------------
# DATABASE & TRACKING HELPERS
# ---------------------------------------------------------

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

# ---------------------------------------------------------
# PERMISSION WRAPPERS
# ---------------------------------------------------------

def is_admin(user_id: int) -> bool:
    return db.is_admin(user_id)

def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not is_admin(user.id):
            await update.message.reply_text("⛔️ អ្នកមិនមានសិទ្ធិប្រើប្រាស់មុខងារនេះទេ (Admin Only)។")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ---------------------------------------------------------
# COMMAND HANDLERS
# ---------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return await update.message.reply_text(
            f"👋 សួស្តី {user.first_name}!\n"
            "នេះជា Admin Bot សម្រាប់គ្រប់គ្រងហាង។ (Admin Only)"
        )
    
    text = (
        "🛠 **ផ្ទាំងគ្រប់គ្រង Admin Dashboard**\n\n"
        "📦 **ទំនិញ (Items):**\n"
        "• /items — មើលទំនិញទាំងអស់\n"
        "• /deleteitem <id> — លុបទំនិញ\n\n"
        "🧾 **ការបញ្ជាទិញ (Orders):**\n"
        "• /orders — មើល Order ដែលកំពុងរង់ចាំ\n\n"
        "📊 **ស្ថិតិ & ប្រកាស (Stats & Broadcast):**\n"
        "• /stats — មើលចំនួន User និងចំណូល\n"
        "• /broadcast <msg> — ផ្ញើសារដំណឹងទៅកាន់ User ទាំងអស់\n"
        "• /spinclaims — មើលអ្នកឈ្នះរង្វាន់ Spin"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

@admin_required
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM bot_users")
    total_users = cur.fetchone()[0]

    day_ago = int(time.time()) - 86400
    cur.execute("SELECT COUNT(*) FROM bot_users WHERE last_seen >= ?", (day_ago,))
    active_today = cur.fetchone()[0]

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

@admin_required
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()
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

    if not user_ids:
        return await update.message.reply_text("❌ មិនទាន់មាន User នៅក្នុង Database ទេ។")

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
                failed += 1
        await asyncio.sleep(1)

    await update.message.reply_text(f"Done. Sent: {sent}, failed/blocked: {failed}.")

@admin_required
async def orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = db.get_pending_orders()
    if not orders:
        return await update.message.reply_text("✨ គ្មាន Order កំពុងរង់ចាំអនុម័តទេ។")
    
    for o in orders:
        item = db.get_item(o["item_id"])
        caption = (
            f"🧾 Order #{o['id']}\n"
            f"👤 អ្នកទិញ: @{o['buyer_username'] or 'N/A'} (ID: `{o['buyer_chat_id']}`)\n"
            f"📦 ទំនិញ: {o['item_name']}\n"
            f"💵 តម្លៃ: {format_price(item['price'] if item else 0, CURRENCY)}"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ អនុម័ត (Approve)", callback_data=f"appr_{o['id']}"),
                InlineKeyboardButton("❌ បដិសេធ (Reject)", callback_data=f"rej_{o['id']}")
            ]
        ])
        
        photo_path = o.get("payment_photo_path")
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, "rb") as f:
                await update.message.reply_photo(f, caption=caption, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(caption, parse_mode="Markdown", reply_markup=kb)

@admin_required
async def items_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = db.list_all_items()
    if not items:
        return await update.message.reply_text("📦 មិនទាន់មានទំនិញនៅក្នុងហាងទេ។")
    
    lines = ["📦 **បញ្ជីទំនិញទាំងអស់:**\n"]
    for it in items:
        status = "🟢 Active" if it["active"] and it["quantity"] > 0 else "🔴 Inactive/Out of stock"
        lines.append(f"• ID #{it['id']} — **{it['name']}** ({it['category']})\n  💵 {format_price(it['price'], CURRENCY)} | ស្តុក: {it['quantity']} | {status}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

@admin_required
async def deleteitem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("ប្រើ: `/deleteitem <item_id>`", parse_mode="Markdown")
    item_id = int(context.args[0])
    db.delete_item(item_id)
    await update.message.reply_text(f"✅ បានលុបទំនិញ ID #{item_id} រួចរាល់។")

@admin_required
async def spinclaims_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    claims = db.list_unclaimed_spins()
    if not claims:
        return await update.message.reply_text("🎡 គ្មាន Spin Win ដែលមិនទាន់ប្រគល់ជូនទេ។")
    
    lines = ["🎡 **បញ្ជីអ្នកឈ្នះ Spin:**\n"]
    for c in claims:
        lines.append(f"• Claim #{c['id']} — @{c['username'] or 'N/A'} (ID: `{c['user_id']}`)\n  🎁 រង្វាន់: **{c['item_name']}**")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ---------------------------------------------------------
# CALLBACK HANDLERS
# ---------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user

    if not is_admin(user.id):
        return await query.message.reply_text("⛔️ អ្នកមិនមានសិទ្ធិទេ។")

    store_bot = Bot(token=STORE_BOT_TOKEN)

    if data.startswith("appr_"):
        order_id = int(data.split("_")[1])
        order = db.get_order(order_id)
        if not order or order["status"] != "pending":
            return await query.edit_message_caption("⚠️ Order នេះត្រូវបានដំណើរការរួចហើយ។")

        db.approve_order(order_id)
        item = db.get_item(order["item_id"])

        if item and item["category"] == "Account":
            db.add_spin_credit(order["buyer_chat_id"], 1)

        await query.edit_message_caption(f"{query.message.caption}\n\n✅ **បានអនុម័តដោយ @{user.username}**", parse_mode="Markdown")

        delivery_text = f"🎉 **Order #{order_id} ត្រូវបានអនុម័ត!**\n\n📦 ទំនិញ: **{order['item_name']}**\n"
        if item and item.get("account_data"):
            delivery_text += f"\n🔐 **ពត៌មានគណនី (Credentials):**\n`{item['account_data']}`\n"
            if item.get("totp_secret"):
                code = get_totp_code(item["totp_secret"])
                delivery_text += f"\n⏱ 2FA Code បច្ចុប្បន្ន: `{code}`\n(ប្រើ /getcode {order_id} ដើម្បីយក Code ថ្មី)"
        else:
            delivery_text += "\nសូមទាក់ទងមក Admin ដើម្បីទទួលការ Trade ក្នុងហ្គេម!"

        try:
            await store_bot.send_message(order["buyer_chat_id"], delivery_text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to notify buyer {order['buyer_chat_id']}: {e}")

    elif data.startswith("rej_"):
        order_id = int(data.split("_")[1])
        order = db.get_order(order_id)
        if not order or order["status"] != "pending":
            return await query.edit_message_caption("⚠️ Order នេះត្រូវបានដំណើរការរួចហើយ។")

        db.reject_order(order_id)
        await query.edit_message_caption(f"{query.message.caption}\n\n❌ **បានបដិសេធដោយ @{user.username}**", parse_mode="Markdown")

        try:
            await store_bot.send_message(
                order["buyer_chat_id"], 
                f"❌ ការទូទាត់សម្រាប់ Order #{order_id} ត្រូវបានបដិសេធ។ សូមទាក់ទងម្ចាស់ហាងប្រសិនបើមានការភាន់ច្រឡំ។"
            )
        except Exception as e:
            logger.warning(f"Failed to notify buyer {order['buyer_chat_id']}: {e}")

async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Admin bot error", exc_info=context.error)

# ---------------------------------------------------------
# APPLICATION BUILDER
# ---------------------------------------------------------

def build_app():
    ensure_tables()
    app = Application.builder().token(ADMIN_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("orders", orders_cmd))
    app.add_handler(CommandHandler("items", items_cmd))
    app.add_handler(CommandHandler("deleteitem", deleteitem_cmd))
    app.add_handler(CommandHandler("spinclaims", spinclaims_cmd))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CallbackQueryHandler(handle_callback, pattern=r"^(appr|rej)_\d+$"))
    
    app.add_error_handler(on_error)
    return app


if __name__ == "__main__":
    db.init_db()
    build_app().run_polling()
