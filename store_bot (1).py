import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, WebAppInfo
from premium_emoji import entities_for
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

import database as db
from config import (STORE_BOT_TOKEN, ADMIN_BOT_TOKEN, CATEGORIES, STORE_NAME, CURRENCY,
                     ADMIN_CONTACT_USERNAME, CREATOR_NAME, CREATOR_YOUTUBE, WEBAPP_URL)
from utils import (format_price, save_telegram_photo, warranty_status, generate_khqr_image,
                    pick_weighted_spin, get_totp_code)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CREDIT_LINE = f"🙏 Video/Guide ដោយ {CREATOR_NAME} — YouTube: {CREATOR_YOUTUBE}"

DEFAULT_RULES = (
    "📜 វិធាន និង Warranty\n\n"
    "🍎 Fruit / 🎮 Gamepass / ទំនិញផ្សេងទៀត (Trade ក្នុងហ្គេម):\n"
    "ការទិញជា Trade ភ្លាមៗក្នុងហ្គេម — ពេលទទួលរួច មិនអាចដូរ ឬសងប្រាក់វិញបានទេ សូមពិនិត្យមុនទទួល។\n\n"
    "📦 Account — Warranty 14ថ្ងៃ (Standard):\n"
    "- បើអ្នកទិញលុប Authenticator App ចោល → Warranty កាត់មកនៅត្រឹម 7ថ្ងៃប៉ុណ្ណោះ\n"
    "- ការសង/ដូរ Account សងតែក្នុងករណី Roblox Support ដកហូត Account មកវិញ (Owner ដើម Revert) ប៉ុណ្ណោះ\n"
    "- បើអ្នកទិញលុប Email សង្គ្រោះ ឬ Code Authenticator App ចោលទាំងអស់ → គ្មាន Warranty ឬសងប្រាក់វិញក្នុងករណីណាមួយឡើយ"
)


def contact_kb(extra_rows=None):
    rows = extra_rows or []
    rows.append([InlineKeyboardButton("📞 ទាក់ទងម្ចាស់ហាង", url=f"https://t.me/{ADMIN_CONTACT_USERNAME}")])
    return InlineKeyboardMarkup(rows)


TEXTS = {
    "km": {
        "welcome": lambda: f"🛒 សូមស្វាគមន៍មកកាន់ {STORE_NAME} 🇰🇭\nហាងលក់ Account / Fruit / Gamepass Blox Fruits ដ៏ទុកចិត្តបាន!",
        "howto": ("📖 របៀបទិញ:\n"
                  "1️⃣ ជ្រើសរើសប្រភេទខាងក្រោម\n"
                  "2️⃣ ចុច 🛍 ទិញឥឡូវ លើមុខទំនិញ\n"
                  "3️⃣ ស្កេន QR ទូទាត់ → ចុច ✅ បញ្ជាក់\n"
                  "4️⃣ ផ្ញើ Screenshot ទូទាត់\n"
                  "5️⃣ រង់ចាំ Admin អនុម័ត → ទទួលទំនិញ!"),
        "help_cmds": ("🎮 ជំនួយបន្ថែម:\n"
                      "/codes 🎁 Code | /tierlist 🍈 Tier | /guide 📺 Video\n"
                      "/rules 📜 វិធាន | /myorders 🧾 Order របស់ខ្ញុំ | /getcode 🔐 លេខ 2FA | /language 🌐 ភាសា"),
        "pick": "👇 សូមជ្រើសរើសប្រភេទ ដើម្បីទិញ:",
    },
    "en": {
        "welcome": lambda: f"🛒 Welcome to {STORE_NAME} 🇰🇭\nTrusted Blox Fruits Account / Fruit / Gamepass store!",
        "howto": ("📖 How to buy:\n"
                  "1️⃣ Pick a category below\n"
                  "2️⃣ Tap 🛍 Buy Now on an item\n"
                  "3️⃣ Scan the QR to pay → tap ✅ Confirm\n"
                  "4️⃣ Send your payment screenshot\n"
                  "5️⃣ Wait for admin approval → get your item!"),
        "help_cmds": ("🎮 More help:\n"
                      "/codes 🎁 Codes | /tierlist 🍈 Tier list | /guide 📺 Videos\n"
                      "/rules 📜 Rules | /myorders 🧾 My orders | /getcode 🔐 2FA code | /language 🌐 Language"),
        "pick": "👇 Pick a category to buy:",
    },
}


def t(chat_id):
    return TEXTS.get(db.get_user_lang(chat_id), TEXTS["km"])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    db.track_user(user.id, user.username)

    if context.args and context.args[0].startswith("buy_") and context.args[0].split("_")[1].isdigit():
        item_id = int(context.args[0].split("_")[1])
        return await send_buy_prompt(update.message, context, item_id)

    tt = t(user.id)
    text = f"{tt['welcome']()}\n\n{tt['howto']}\n\n{tt['help_cmds']}"
    kb = []
    if WEBAPP_URL:
        kb.append([InlineKeyboardButton("✨ ចូល Uchiro Store App", web_app=WebAppInfo(url=WEBAPP_URL))])
    await update.message.reply_text(text, reply_markup=contact_kb(kb))


async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇰🇭 ខ្មែរ", callback_data="lang_km"),
                                 InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]])
    await update.message.reply_text("ជ្រើសរើសភាសា / Choose your language:", reply_markup=kb)


async def language_select_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_", 1)[1]
    db.set_user_lang(update.effective_user.id, lang)
    msg = "✅ ភាសាត្រូវបានប្តូរទៅជា ខ្មែរ! ប្រើ /start ដើម្បីមើលម្តងទៀត។" if lang == "km" \
        else "✅ Language switched to English! Use /start to see the updated menu."
    await query.message.reply_text(msg)


async def myorders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = db.get_orders_by_buyer(update.effective_user.id, 20)
    if not orders:
        return await update.message.reply_text("អ្នកមិនទាន់មាន Order ណាទេ។ ប្រើ /start ដើម្បីទិញ។")
    icon = {"pending": "⏳ កំពុងរង់ចាំ", "approved": "✅ អនុម័តរួច", "rejected": "❌ បដិសេធ"}
    lines = ["🧾 Order របស់អ្នក:\n"]
    for o in orders:
        line = f"#{o['id']} {o['item_name']} — {icon.get(o['status'], o['status'])}"
        if o["status"] == "approved":
            w = warranty_status(o["approved_at"], o["warranty_days"])
            if w:
                line += f"\n   {w}"
        lines.append(line)
    await update.message.reply_text("\n".join(lines))


async def getcode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/getcode <order_id> - refresh the live 2FA code for an approved Account order,
    for whenever the buyer's own authenticator app isn't handy yet."""
    if not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("ប្រើ: /getcode <order_id> (លេខ Order របស់អ្នក, មើលបានតាម /myorders)")
    order_id = int(context.args[0])
    order = db.get_order(order_id)
    if not order or order["buyer_chat_id"] != update.effective_user.id or order["status"] != "approved":
        return await update.message.reply_text("រកមិនឃើញ Order នេះ ឬ Order នេះមិនទាន់អនុម័តទេ។")
    item = db.get_item(order["item_id"])
    secret = item["totp_secret"] if item and "totp_secret" in item.keys() else ""
    if not secret:
        return await update.message.reply_text("គណនីនេះមិនប្រើ Authenticator 2FA ទេ។")
    code = get_totp_code(secret)
    if not code:
        return await update.message.reply_text("មិនអាចបង្កើត Code បានទេ។ សូមទាក់ទងម្ចាស់ហាង។")
    await update.message.reply_text(f"⏱ លេខ 2FA បច្ចុប្បន្ន: `{code}`\n(ប្តូរជារៀងរាល់ 30វិនាទី — ចម្លងលឿនៗ)", parse_mode="Markdown")


async def shop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not WEBAPP_URL:
        return await update.message.reply_text("Mini App មិនទាន់បើកដំណើរការទេ។ សូមប្រើ /start ជំនួសសិន។")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛍 បើក Uchiro Store App", web_app=WebAppInfo(url=WEBAPP_URL))]])
    await update.message.reply_text("ចុចប៊ូតុងខាងក្រោមដើម្បីបើក Store App ថ្មី! 🎮✨", reply_markup=kb)


async def support_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ត្រូវការជំនួយ? ចុចប៊ូតុងខាងក្រោមដើម្បីទាក់ទងម្ចាស់ហាងផ្ទាល់៖", reply_markup=contact_kb())


async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules = db.get_setting("rules_text", DEFAULT_RULES)
    await update.message.reply_text(rules)


async def spin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    credits = db.get_spin_credits(user.id)
    if credits < 1:
        return await update.message.reply_text(
            "🎡 អ្នកមិនទាន់មាន Spin ទេ!\n\n"
            "ទិញ Account ណាមួយ ហើយ Admin អនុម័តរួច អ្នកនឹងទទួល **Spin ឥតគិតថ្លៃ 1 ដង** ស្វ័យប្រវត្តិ 🎁",
            parse_mode="Markdown"
        )
    pool = db.list_spin_items()
    if not pool:
        return await update.message.reply_text("🎡 Spin Pool មិនទាន់មានទំនិញទេ។ សូមទាក់ទងម្ចាស់ហាង។")

    db.consume_spin_credit(user.id)
    won = pick_weighted_spin(pool)
    win_id = db.record_spin_win(user.id, user.username, won["name"])

    await update.message.reply_text(
        f"🎉🎡 អបអរសាទរ! អ្នកឈ្នះ: **{won['name']}**!\n\n"
        f"🧾 Claim ID: #{win_id}\n"
        "សូមទាក់ទងម្ចាស់ហាងដើម្បីទទួលរង្វាន់របស់អ្នក 👇",
        parse_mode="Markdown", reply_markup=contact_kb()
    )

    admin_bot = Bot(token=ADMIN_BOT_TOKEN)
    for admin_id in db.all_admin_ids():
        try:
            await admin_bot.send_message(
                admin_id,
                f"🎡 Spin Win ថ្មី #{win_id}\n👤 @{user.username or 'N/A'} (id: {user.id})\n🎁 {won['name']}\n\nប្រើ /spinclaims ដើម្បីប្រគល់ជូន"
            )
        except Exception as e:
            logger.warning(f"notify admin {admin_id} of spin win failed: {e}")


async def codes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    codes = db.get_setting("codes_text")
    if not codes:
        return await update.message.reply_text("😅 មិនទាន់មាន Code ថ្មីទេ! សូមចាំមើលពេលក្រោយ។")
    text = (f"🎁 Code ថ្មីៗ សម្រាប់ Blox Fruits!\n\n{codes}\n\n"
            "👉 របៀបប្រើ: ចូលហ្គេម → ចុច Setting (រូប Gear) → Redeem Code → Paste Code → Enter")
    try:
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(text)


async def tierlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tierlist = db.get_setting("tierlist_text")
    if not tierlist:
        return await update.message.reply_text("😅 មិនទាន់មាន Tier List ទេ! សូមចាំមើលពេលក្រោយ។")
    text = f"🍈 Fruit Tier List (ល្អទៅមិនល្អ):\n\n{tierlist}"
    try:
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(text)


async def guide_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    guides = db.list_guides()
    if not guides:
        return await update.message.reply_text("😅 មិនទាន់មាន Guide ទេ! សូមចាំមើលពេលក្រោយ។")
    kb = [[InlineKeyboardButton(g["title"], callback_data=f"guide_{g['id']}")] for g in guides]
    await update.message.reply_text(f"📺 ជ្រើសរើស Guide ដែលចង់មើល:\n{CREDIT_LINE}", reply_markup=InlineKeyboardMarkup(kb))


async def guide_select_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    guide_id = int(query.data.split("_")[1])
    g = db.get_guide(guide_id)
    if not g:
        return await query.message.reply_text("រកមិនឃើញ Guide នេះទេ។")
    await query.message.reply_text(f"📺 {g['title']}\n▶️ {g['video_url']}\n\n{CREDIT_LINE}")


async def category_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.split("_", 1)[1]
    items = db.get_items_by_category(category)
    if not items:
        return await query.message.reply_text(f"📦 {category} — មិនទាន់មានស្តុកទេ។")

    if category == "Account":
        for it in items:
            caption = (f"📦 {it['category']} — {it['name']}\n💵 {format_price(it['price'], CURRENCY)}\n"
                       f"📝 {it['description']}\n📊 ស្តុកនៅសល់: {it['quantity']}")
            if it["warranty_days"]:
                caption += f"\n🛡️ Warranty {it['warranty_days']}ថ្ងៃ"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛍 ទិញឥឡូវ", callback_data=f"buy_{it['id']}")]])
            photo_path = it["photo_file_id"]
            if photo_path and os.path.exists(photo_path):
                with open(photo_path, "rb") as f:
                    await query.message.reply_photo(f, caption=caption, reply_markup=kb)
            else:
                await query.message.reply_text(caption, reply_markup=kb)
        return

    lines = [f"📦 ស្តុក {category} ទាំងអស់:\n"]
    for idx, it in enumerate(items, start=1):
        lines.append(f"Option {idx}: {it['name']} — {format_price(it['price'], CURRENCY)} (ស្តុក {it['quantity']})")
    lines.append("\nចុចលេខខាងក្រោមដើម្បីទិញ:")

    buttons, row = [], []
    for idx, it in enumerate(items, start=1):
        row.append(InlineKeyboardButton(str(idx), callback_data=f"buy_{it['id']}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await query.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def applycoupon_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        return await update.message.reply_text("ប្រើ: /applycoupon <code>\nឧ. /applycoupon SAVE20")
    code = context.args[0].strip().upper()
    coupon, error = db.validate_coupon(code, user.id)
    if error == "not_found":
        return await update.message.reply_text("❌ Coupon នេះមិនត្រឹមត្រូវ ឬផុតកំណត់ទេ។")
    if error == "exhausted":
        return await update.message.reply_text("❌ Coupon នេះប្រើអស់ហើយ (លើសចំនួនកំណត់)។")
    if error == "already_used":
        return await update.message.reply_text("❌ អ្នកបានប្រើ Coupon នេះរួចហើយ (ប្រើបានតែ 1ដងក្នុងម្នាក់)។")
    context.user_data["coupon_code"] = code
    unit = "%" if coupon["discount_type"] == "percent" else CURRENCY
    await update.message.reply_text(
        f"✅ Coupon {code} ត្រូវបានអនុវត្ត! បញ្ចុះតម្លៃ {coupon['amount']}{unit}\n"
        "ចុច 🛍 ទិញឥឡូវ លើមុខទំនិញណាមួយ — Discount នឹងអនុវត្តស្វ័យប្រវត្តិលើការទិញបន្ទាប់នេះ។"
    )


async def send_buy_prompt(message, context: ContextTypes.DEFAULT_TYPE, item_id: int):
    item = db.get_item(item_id)
    if not item or not item["active"] or item["quantity"] <= 0:
        return await message.reply_text("សូមអភ័យទោស ទំនិញនេះអស់ស្តុកហើយ។")

    price_text = format_price(item["price"], CURRENCY)
    note = db.get_setting("payment_note", "")

    caption = f"🛍 អ្នកបានជ្រើសរើស: {item['name']}\n💵 សូមទូទាត់: {price_text}"
    if item["warranty_days"]:
        caption += f"\n🛡️ Warranty {item['warranty_days']}ថ្ងៃ (ចាប់ពីពេលអនុម័ត)"

    # Try a real KHQR with the exact amount baked in first (better UX - amount auto-fills
    # in the buyer's banking app). Falls back to the static uploaded QR photo if not configured.
    khqr_account = db.get_setting("khqr_account_id")
    qr_path = None
    if khqr_account:
        qr_path = generate_khqr_image(
            khqr_account, db.get_setting("khqr_merchant_name", "Uchiro Store"),
            db.get_setting("khqr_merchant_city", "Phnom Penh"), item["price"], f"ORDER{item_id}"
        )
        if qr_path:
            caption += "\n\n📱 ស្កេន KHQR ខាងក្រោម — តម្លៃបំពេញស្វ័យប្រវត្តិ!"
    if not qr_path:
        qr_path = db.get_setting("qr_photo_path")
        caption += "\n\n📱 ស្កេន QR ខាងក្រោមដើម្បីទូទាត់"

    if note:
        caption += f"\n{note}"
    caption += "\n\n✅ ទូទាត់រួច សូមចុចប៊ូតុង \"បញ្ជាក់\" ខាងក្រោម"

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ បញ្ជាក់ (ខ្ញុំបានទូទាត់)", callback_data=f"confirmbuy_{item_id}"),
                                 InlineKeyboardButton("❌ បោះបង់", callback_data="cancelbuy")]])
    if qr_path and os.path.exists(qr_path):
        with open(qr_path, "rb") as f:
            await message.reply_photo(f, caption=caption, reply_markup=kb)
    else:
        caption += "\n\n(ម្ចាស់ហាងមិនទាន់កំណត់ QR ទេ សូមទាក់ទងផ្ទាល់)"
        await message.reply_text(caption, reply_markup=kb)


async def buy_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db.track_user(update.effective_user.id, update.effective_user.username)
    item_id = int(query.data.split("_")[1])
    await send_buy_prompt(query.message, context, item_id)


async def confirm_buy_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_id = int(query.data.split("_")[1])
    item = db.get_item(item_id)
    if not item or not item["active"] or item["quantity"] <= 0:
        return await query.message.reply_text("សូមអភ័យទោស ទំនិញនេះអស់ស្តុកហើយ។")
    context.user_data["buy_item_id"] = item_id
    context.user_data["state"] = "await_payment"
    await query.message.reply_text("សូមផ្ញើរូបភាព Screenshot នៃការទូទាត់មកទីនេះ:")


async def cancel_buy_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.reply_text("បានបោះបង់ការទិញ។ ប្រើ /start ដើម្បីមើលទំនិញម្តងទៀត។")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != "await_payment":
        return
    item_id = context.user_data.get("buy_item_id")
    item = db.get_item(item_id)
    if not item:
        context.user_data.clear()
        return await update.message.reply_text("មានបញ្ហា សូម /start ម្តងទៀត។")

    file_id = update.message.photo[-1].file_id
    payment_photo_path = await save_telegram_photo(context.bot, file_id, "payments")
    buyer = update.effective_user
    order_id = db.create_order(item_id, buyer.id, buyer.username, payment_photo_path)
    context.user_data.clear()

    await update.message.reply_text(f"✅ បានទទួល Order #{order_id}! សូមរង់ចាំម្ចាស់ហាងផ្ទៀងផ្ទាត់។")

    admin_bot = Bot(token=ADMIN_BOT_TOKEN)
    caption = (f"🧾 Order ថ្មី #{order_id}\n👤 @{buyer.username or 'N/A'} (id: {buyer.id})\n"
               f"📦 {item['name']}\n💵 {format_price(item['price'], CURRENCY)}")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ អនុម័ត", callback_data=f"appr_{order_id}"),
                                 InlineKeyboardButton("❌ បដិសេធ", callback_data=f"rej_{order_id}")]])
    for admin_id in db.all_admin_ids():
        try:
            with open(payment_photo_path, "rb") as f:
                await admin_bot.send_photo(admin_id, f, caption=caption, reply_markup=kb)
        except Exception as e:
            logger.warning(f"notify admin {admin_id} failed: {e}")


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Store bot error", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(update.effective_chat.id, "⚠️ មានបញ្ហាបច្ចេកទេស សូមព្យាយាមម្តងទៀត ឬចុច /start")
    except Exception:
        pass


def build_app():
    app = Application.builder().token(STORE_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("shop", shop_cmd))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CommandHandler("myorders", myorders_cmd))
    app.add_handler(CommandHandler("getcode", getcode_cmd))
    app.add_handler(CommandHandler("spin", spin_cmd))
    app.add_handler(CommandHandler("applycoupon", applycoupon_cmd))
    app.add_handler(CommandHandler("support", support_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("codes", codes_cmd))
    app.add_handler(CommandHandler("tierlist", tierlist_cmd))
    app.add_handler(CommandHandler("guide", guide_cmd))
    app.add_handler(CallbackQueryHandler(guide_select_cb, pattern=r"^guide_\d+$"))
    app.add_handler(CallbackQueryHandler(language_select_cb, pattern=r"^lang_(km|en)$"))
    app.add_handler(CallbackQueryHandler(category_cb, pattern=r"^cat_"))
    app.add_handler(CallbackQueryHandler(buy_cb, pattern=r"^buy_\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_buy_cb, pattern=r"^confirmbuy_\d+$"))
    app.add_handler(CallbackQueryHandler(cancel_buy_cb, pattern=r"^cancelbuy$"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_error_handler(on_error)
    return app


if __name__ == "__main__":
    db.init_db()
    build_app().run_polling()
