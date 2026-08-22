"""
Web server for the Uchiro Store Telegram Mini App.
Serves the mini app UI + a read-only JSON API that reads from the same store.db
used by the bots. Also serves product photos from the local media/ folder.

Run standalone for local testing:
    python webapp_server.py
In production this is started by main.py alongside the bots (same process,
different thread) when WEBAPP_PORT is set.
"""
import os
import uuid
import asyncio
from flask import Flask, jsonify, render_template, send_from_directory, request
from premium_emoji import entities_for
import database as db
from config import (STORE_BOT_USERNAME, CATEGORIES, STORE_CHANNEL_USERNAME, STORE_BOT_TOKEN,
                     ADMIN_BOT_TOKEN, CURRENCY, ADMIN_CONTACT_USERNAME)
from utils import (format_price, generate_khqr_image, generate_khqr_with_md5,
                    verify_webapp_init_data, check_khqr_paid, build_delivery_message)

app = Flask(__name__, template_folder="webapp/templates")

ASSETS_DIR = os.path.join(os.getcwd(), "webapp", "assets")


@app.route("/")
def index():
    logo_path = os.path.join(ASSETS_DIR, "logo.png")
    music_path = os.path.join(ASSETS_DIR, "music.mp3")
    return render_template(
        "index.html",
        bot_username=STORE_BOT_USERNAME,
        channel_username=STORE_CHANNEL_USERNAME,
        admin_username=ADMIN_CONTACT_USERNAME,
        logo_url="/assets/logo.png" if os.path.exists(logo_path) else None,
        music_url="/assets/music.mp3" if os.path.exists(music_path) else None,
    )


@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(ASSETS_DIR, filename)


@app.route("/api/items")
def api_items():
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=3)
    items = []
    for it in db.get_published_items():
        # photo_file_id is stored as a relative path like "media/items/xxxx.jpg"
        photo_url = f"/{it['photo_file_id']}" if it["photo_file_id"] else None
        is_new = False
        if it["released_at"]:
            try:
                is_new = datetime.strptime(it["released_at"], "%Y-%m-%d %H:%M:%S") > cutoff
            except ValueError:
                pass
        items.append({
            "id": it["id"],
            "category": it["category"],
            "name": it["name"],
            "price": it["price"],
            "description": it["description"],
            "quantity": it["quantity"],
            "warranty_days": it["warranty_days"],
            "photo_url": photo_url,
            "is_new": is_new,
        })
    return jsonify({"items": items, "categories": CATEGORIES})


@app.route("/media/<path:filename>")
def media(filename):
    return send_from_directory(os.path.join(os.getcwd(), "media"), filename)


def _notify_admins_of_order(order_id):
    """Send the payment screenshot + Approve/Reject buttons to every admin, reusing the
    exact same callback_data pattern (appr_<id>/rej_<id>) that admin_bot.order_decision_cb
    already handles - so approval, warranty start, stock decrement, and the Telegram-chat
    delivery message all keep working exactly as before, no duplicated logic."""
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

    async def _send():
        order = db.get_order(order_id)
        item = db.get_item(order["item_id"]) if order else None
        if not order or not item:
            return
        bot = Bot(token=ADMIN_BOT_TOKEN)
        caption = (f"🧾 Order ថ្មី (Mini App) #{order_id}\n👤 @{order['buyer_username'] or 'N/A'} (id: {order['buyer_chat_id']})\n"
                   f"📦 {item['name']}\n💵 {format_price(item['price'], CURRENCY)}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ អនុម័ត", callback_data=f"appr_{order_id}"),
                                     InlineKeyboardButton("❌ បដិសេធ", callback_data=f"rej_{order_id}")]])
        photo_path = order["payment_photo_file_id"]
        for admin_id in db.all_admin_ids():
            try:
                if photo_path and os.path.exists(photo_path):
                    with open(photo_path, "rb") as f:
                        await bot.send_photo(admin_id, f, caption=caption, reply_markup=kb)
                else:
                    await bot.send_message(admin_id, caption, reply_markup=kb)
            except Exception as e:
                print(f"notify admin {admin_id} failed: {e}")

    asyncio.run(_send())


@app.route("/api/order/quote", methods=["POST"])
def api_order_quote():
    data = request.get_json(force=True) or {}
    item = db.get_item(data.get("item_id"))
    if not item or not item["active"] or item["quantity"] <= 0:
        return jsonify({"error": "out_of_stock"}), 400

    qr_path, khqr_md5 = None, None
    khqr_account = db.get_setting("khqr_account_id")
    if khqr_account:
        qr_path, khqr_md5 = generate_khqr_with_md5(
            khqr_account, db.get_setting("khqr_merchant_name", "Uchiro Store"),
            db.get_setting("khqr_merchant_city", "Phnom Penh"), item["price"], f"WEB{item['id']}"
        )
    if not qr_path:
        qr_path = db.get_setting("qr_photo_path")

    return jsonify({
        "item_id": item["id"],
        "name": item["name"],
        "price": item["price"],
        "warranty_days": item["warranty_days"],
        "qr_url": f"/{qr_path}" if qr_path and os.path.exists(qr_path) else None,
        # Frontend must send this back unchanged in /api/order/submit so the backend
        # can poll Bakong for *this exact* bill later and auto-approve on payment.
        "khqr_md5": khqr_md5,
        "note": db.get_setting("payment_note", ""),
    })


@app.route("/api/order/submit", methods=["POST"])
def api_order_submit():
    init_data = request.form.get("init_data", "")
    item_id = request.form.get("item_id", type=int)
    khqr_md5 = request.form.get("khqr_md5") or None  # from the /api/order/quote response, if KHQR was shown
    photo = request.files.get("photo")

    user = verify_webapp_init_data(init_data, STORE_BOT_TOKEN)
    if not user:
        return jsonify({"error": "invalid_auth"}), 401
    if not item_id or not photo:
        return jsonify({"error": "missing_fields"}), 400

    item = db.get_item(item_id)
    if not item or not item["active"] or item["quantity"] <= 0:
        return jsonify({"error": "out_of_stock"}), 400

    folder = os.path.join("media", "payments")
    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(photo.filename or "")[1] or ".jpg"
    save_path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
    photo.save(save_path)

    order_id = db.create_order(item_id, user["id"], user.get("username"), save_path)
    if khqr_md5:
        db.set_order_khqr_md5(order_id, khqr_md5)
    try:
        _notify_admins_of_order(order_id)
    except Exception as e:
        print(f"admin notify error: {e}")

    return jsonify({"order_id": order_id})


def _auto_approve_and_deliver(order_id, order, item):
    """Same effect as an admin tapping ✅ in the bot, triggered by a confirmed
    Bakong payment instead of a manual tap. Notifies the buyer over Telegram too,
    per the brief's 'chat as backup channel' requirement."""
    db.set_order_approved(order_id)
    db.decrement_stock(item["id"])
    if item["category"] == "Account":
        db.grant_spin_credit(order["buyer_chat_id"], 1)
    try:
        from telegram import Bot
        msg = "🎉 ការទូទាត់ត្រូវបានផ្ទៀងផ្ទាត់ស្វ័យប្រវត្តិ! អរគុណដែលទិញនៅ Uchiro Store 🇰🇭\n\n" + build_delivery_message(item)
        bot = Bot(token=STORE_BOT_TOKEN)

        async def _send():
            try:
                await bot.send_message(order["buyer_chat_id"], msg, parse_mode="Markdown")
            except Exception:
                await bot.send_message(order["buyer_chat_id"], msg)
        asyncio.run(_send())
    except Exception as e:
        print(f"auto-approve notify error: {e}")


@app.route("/api/order/<int:order_id>/status")
def api_order_status(order_id):
    init_data = request.args.get("init_data", "")
    user = verify_webapp_init_data(init_data, STORE_BOT_TOKEN)
    order = db.get_order(order_id)
    if not order or not user or order["buyer_chat_id"] != user["id"]:
        return jsonify({"error": "not_found"}), 404

    # While still pending and we have a khqr_md5 on file, check with Bakong whether
    # this exact bill has actually been paid yet. True -> auto-approve right now.
    # False/None (unpaid, no token, network hiccup) -> leave it pending; manual
    # admin review in the bot always remains the fallback, nothing is ever stuck.
    if order["status"] == "pending" and order["khqr_md5"]:
        paid = check_khqr_paid(order["khqr_md5"])
        if paid:
            item = db.get_item(order["item_id"])
            if item and item["active"] and item["quantity"] > 0:
                _auto_approve_and_deliver(order_id, order, item)
                order = db.get_order(order_id)

    resp = {"status": order["status"], "order_id": order["id"]}
    if order["status"] == "approved":
        item = db.get_item(order["item_id"])
        resp["delivery_info"] = build_delivery_message(item) if item else ""
        resp["item_name"] = item["name"] if item else ""
        resp["has_totp"] = bool(item and item["totp_secret"]) if item else False
    return jsonify(resp)


@app.route("/api/order/<int:order_id>/refresh-code")
def api_order_refresh_code(order_id):
    """Called by the Mini App's 'Refresh Code' button once the stale 30s code in the
    original delivery message no longer works - returns a fresh live TOTP code."""
    init_data = request.args.get("init_data", "")
    user = verify_webapp_init_data(init_data, STORE_BOT_TOKEN)
    order = db.get_order(order_id)
    if not order or not user or order["buyer_chat_id"] != user["id"] or order["status"] != "approved":
        return jsonify({"error": "not_found"}), 404
    item = db.get_item(order["item_id"])
    secret = item["totp_secret"] if item else ""
    if not secret:
        return jsonify({"error": "no_totp"}), 400
    from utils import get_totp_code
    code = get_totp_code(secret)
    if not code:
        return jsonify({"error": "generation_failed"}), 500
    return jsonify({"code": code})


@app.route("/api/my-orders")
def api_my_orders():
    init_data = request.args.get("init_data", "")
    user = verify_webapp_init_data(init_data, STORE_BOT_TOKEN)
    if not user:
        return jsonify({"error": "invalid_auth"}), 401
    from utils import warranty_status
    orders = db.get_orders_by_buyer(user["id"], 30)
    out = []
    for o in orders:
        out.append({
            "id": o["id"], "item_name": o["item_name"], "status": o["status"],
            "created_at": o["created_at"],
            "warranty": warranty_status(o["approved_at"], o["warranty_days"]) if o["status"] == "approved" else None,
        })
    return jsonify({"orders": out})


@app.route("/api/rules")
def api_rules():
    default_rules = (
        "📜 វិធាន និង Warranty\n\n"
        "🍎 Fruit / 🎮 Gamepass / ទំនិញផ្សេងទៀត (Trade ក្នុងហ្គេម):\n"
        "ការទិញជា Trade ភ្លាមៗក្នុងហ្គេម — ពេលទទួលរួច មិនអាចដូរ ឬសងប្រាក់វិញបានទេ។\n\n"
        "📦 Account — Warranty 14ថ្ងៃ (Standard):\n"
        "- បើលុប Authenticator App ចោល → Warranty កាត់មកនៅត្រឹម 7ថ្ងៃប៉ុណ្ណោះ\n"
        "- សង/ដូរ Account សងតែក្នុងករណី Roblox Support ដកហូត Account មកវិញប៉ុណ្ណោះ\n"
        "- បើលុប Email/Code Authenticator ចោលទាំងអស់ → គ្មាន Warranty ឬសងប្រាក់វិញឡើយ"
    )
    return jsonify({"rules": db.get_setting("rules_text", default_rules)})


@app.route("/health")
def health():
    return "ok"


# ==================== ADMIN PANEL ====================

def _require_admin(init_data):
    """Verify the Telegram WebApp initData signature AND that this specific user is an
    admin/seller in our own database. Returns the verified user dict, or None."""
    user = verify_webapp_init_data(init_data, ADMIN_BOT_TOKEN)
    if not user or not db.is_admin_id(user["id"]):
        return None
    return user


@app.route("/admin")
def admin_page():
    return render_template("admin.html", categories=CATEGORIES)


@app.route("/api/admin/verify", methods=["POST"])
def api_admin_verify():
    data = request.get_json(force=True) or {}
    user = _require_admin(data.get("init_data", ""))
    return jsonify({"is_admin": bool(user), "name": user.get("first_name") if user else None})


@app.route("/api/admin/items", methods=["GET"])
def api_admin_items_list():
    user = _require_admin(request.args.get("init_data", ""))
    if not user:
        return jsonify({"error": "forbidden"}), 403
    items = []
    for it in db.get_all_items():
        d = dict(it)
        d["photo_url"] = f"/{it['photo_file_id']}" if it["photo_file_id"] else None
        items.append(d)
    return jsonify({"items": items, "categories": CATEGORIES})


@app.route("/api/admin/items", methods=["POST"])
def api_admin_items_create():
    init_data = request.form.get("init_data", "")
    user = _require_admin(init_data)
    if not user:
        return jsonify({"error": "forbidden"}), 403

    category = request.form.get("category", "").strip()
    name = request.form.get("name", "").strip()
    try:
        price = float(request.form.get("price", 0))
        quantity = int(request.form.get("quantity", 1))
        warranty_days = int(request.form.get("warranty_days", 0))
    except ValueError:
        return jsonify({"error": "bad_number"}), 400
    description = request.form.get("description", "").strip()
    delivery_info = request.form.get("delivery_info", "").strip()
    totp_secret = request.form.get("totp_secret", "").strip()

    if not category or not name or price <= 0:
        return jsonify({"error": "missing_fields"}), 400

    photo_path = None
    photo = request.files.get("photo")
    if photo and photo.filename:
        folder = os.path.join("media", "items")
        os.makedirs(folder, exist_ok=True)
        ext = os.path.splitext(photo.filename)[1] or ".jpg"
        photo_path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
        photo.save(photo_path)

    item_id = db.add_item(category, name, price, description, photo_path, delivery_info, quantity, warranty_days)
    if totp_secret:
        db.update_item_field(item_id, "totp_secret", totp_secret)
    return jsonify({"item_id": item_id})


@app.route("/api/admin/items/<int:item_id>", methods=["PATCH"])
def api_admin_items_update(item_id):
    init_data = request.form.get("init_data", "") or (request.get_json(silent=True) or {}).get("init_data", "")
    user = _require_admin(init_data)
    if not user:
        return jsonify({"error": "forbidden"}), 403
    if not db.get_item(item_id):
        return jsonify({"error": "not_found"}), 404

    payload = request.form if request.form else (request.get_json(silent=True) or {})
    allowed = {"name": str, "price": float, "description": str, "quantity": int,
               "delivery_info": str, "totp_secret": str, "active": int, "warranty_days": int}
    clearable = {"delivery_info", "totp_secret"}  # "-" is the clear sentinel, matching the bot's /additem flow
    updated = []
    for field, cast in allowed.items():
        if field not in payload:
            continue
        raw = payload[field]
        if field in clearable and raw == "-":
            db.update_item_field(item_id, field, "")
            updated.append(field)
            continue
        if raw in (None, ""):
            continue
        try:
            db.update_item_field(item_id, field, cast(raw))
            updated.append(field)
        except ValueError:
            return jsonify({"error": f"bad_value_for_{field}"}), 400

    photo = request.files.get("photo") if request.files else None
    if photo and photo.filename:
        folder = os.path.join("media", "items")
        os.makedirs(folder, exist_ok=True)
        ext = os.path.splitext(photo.filename)[1] or ".jpg"
        photo_path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
        photo.save(photo_path)
        db.update_item_field(item_id, "photo_file_id", photo_path)
        updated.append("photo")

    return jsonify({"updated": updated})


@app.route("/api/admin/items/<int:item_id>", methods=["DELETE"])
def api_admin_items_delete(item_id):
    init_data = request.args.get("init_data", "") or (request.get_json(silent=True) or {}).get("init_data", "")
    user = _require_admin(init_data)
    if not user:
        return jsonify({"error": "forbidden"}), 403
    db.delete_item(item_id)
    return jsonify({"deleted": item_id})


@app.route("/api/admin/orders")
def api_admin_orders():
    user = _require_admin(request.args.get("init_data", ""))
    if not user:
        return jsonify({"error": "forbidden"}), 403
    orders = db.get_recent_orders(30)
    return jsonify({"orders": [dict(o) for o in orders]})


def run(port=None):
    port = port or int(os.getenv("WEBAPP_PORT", "8080"))
    db.init_db()
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
