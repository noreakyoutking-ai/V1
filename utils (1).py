import os
import uuid
import random
from datetime import datetime, timedelta
from premium_emoji import entities_for

MEDIA_DIR = "media"


def format_price(price, currency="$"):
    price = float(price)
    if price == int(price):
        return f"{int(price)}{currency}"
    return f"{price:.2f}{currency}"


async def save_telegram_photo(bot, file_id, subdir):
    """Telegram file_ids only work with the bot that received them.
    Since we run multiple bots, download the photo once and re-serve it from disk."""
    folder = os.path.join(MEDIA_DIR, subdir)
    os.makedirs(folder, exist_ok=True)
    tg_file = await bot.get_file(file_id)
    path = os.path.join(folder, f"{uuid.uuid4().hex}.jpg")
    await tg_file.download_to_drive(path)
    return path


def generate_khqr_image(account_id, merchant_name, merchant_city, amount, bill_number):
    """Generate a real Cambodia KHQR (EMV-compliant) with the exact amount baked in,
    so the buyer's banking app auto-fills the correct amount when they scan.
    Returns a local PNG path on success, or None on any failure (caller should fall
    back to the static uploaded QR photo instead)."""
    path, _md5 = generate_khqr_with_md5(account_id, merchant_name, merchant_city, amount, bill_number)
    return path


def generate_khqr_with_md5(account_id, merchant_name, merchant_city, amount, bill_number):
    """Same as generate_khqr_image, but also returns the md5 hash of the QR string.
    That md5 is what Bakong's check_payment API uses to identify *this specific* QR,
    so store it on the order and poll it to know when this exact bill got paid.
    Returns (image_path_or_None, md5_or_None)."""
    try:
        from bakong_khqr import KHQR
    except ImportError:
        return None, None

    try:
        khqr = KHQR()
        qr_string = khqr.create_qr(
            account_id=account_id,
            merchant_name=merchant_name,
            merchant_city=merchant_city or "Phnom Penh",
            amount=float(amount),
            currency="USD",
            store_label="Uchiro Store",
            bill_number=bill_number,
            static=False,
        )
        md5 = khqr.generate_md5(qr_string)
        folder = os.path.join(MEDIA_DIR, "khqr")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{uuid.uuid4().hex}.png")
        khqr.qr_image(qr_string, output_path=path, format="png")
        return (path if os.path.exists(path) else None), md5
    except Exception:
        return None, None


def check_khqr_paid(md5):
    """Ask Bakong whether the bill with this md5 has actually been paid yet.
    Requires BAKONG_API_TOKEN to be set. Returns True/False/None:
      True  -> confirmed paid, safe to auto-approve
      False -> confirmed still unpaid
      None  -> couldn't check right now (no token, network error, etc.) -
               caller should NOT auto-approve on None, just fall back to manual review."""
    token = os.getenv("BAKONG_API_TOKEN")
    if not token or not md5:
        return None
    try:
        from bakong_khqr import KHQR
        khqr = KHQR(token)
        status = khqr.check_payment(md5)  # e.g. "PAID" or "UNPAID"
        if isinstance(status, tuple):
            status = status[0]
        return str(status).upper() == "PAID"
    except Exception:
        return None


def build_delivery_message(item):
    """Build the full delivery text sent to a buyer once their order is approved:
    login info + (if a TOTP secret is on file) step-by-step authenticator setup
    with a live current code, so the buyer can log in immediately."""
    msg = ""
    if item["delivery_info"]:
        msg += f"🔑 {item['delivery_info']}"
    else:
        msg += "ម្ចាស់ហាងនឹងផ្ញើព័ត៌មានឲ្យអ្នកឆាប់ៗ។"

    secret = item["totp_secret"] if "totp_secret" in item.keys() else ""
    if secret:
        code = get_totp_code(secret)
        msg += (
            "\n\n🔐 *Authenticator Setup (2FA)*\n"
            "១. ដំឡើង *Google Authenticator* ឬ *Authy* លើទូរស័ព្ទ\n"
            "២. ជ្រើសរើស \"Enter setup key\" / \"បញ្ចូលដោយដៃ\" (មិនមែន Scan QR ទេ)\n"
            f"៣. វាយបញ្ចូល Key នេះ:\n`{secret}`\n"
            "៤. កំណត់ Account name និង Key type = *Time based*\n"
            "៥. App នឹងបង្ហាញលេខ ៦ខ្ទង់ ដែលប្តូរជារៀងរាល់ 30វិនាទី — លេខនេះហើយប្រើពេល Roblox សួរ 2FA code\n"
        )
        if code:
            msg += f"\n⏱ លេខបច្ចុប្បន្ន (ប្រើភ្លាមៗ): `{code}` _(ផុតកំណត់ក្នុងប៉ុន្មានវិនាទី)_"
        msg += (
            "\n\n⚠️ កុំលុប Authenticator App ចោល — បើលុប Warranty កាត់មកនៅត្រឹម 7ថ្ងៃ "
            "(លុបទាំង Email សង្គ្រោះ ឬ Code ចោលទាំងអស់ = គ្មាន Warranty ទាល់តែសោះ)"
        )
    return msg


def get_totp_code(secret):
    """Compute the current 6-digit authenticator code for a stored TOTP secret,
    so buyers can get a working login code without installing anything themselves
    first if they're in a hurry. Returns None if pyotp isn't installed or the
    secret is empty/invalid."""
    if not secret:
        return None
    try:
        import pyotp
        return pyotp.TOTP(secret.strip()).now()
    except Exception:
        return None


def verify_webapp_init_data(init_data: str, bot_token: str):
    """Validate Telegram WebApp initData per Telegram's documented HMAC scheme, so the
    Mini App backend can trust the telegram user id it receives instead of anyone being
    able to POST orders as an arbitrary user. Returns the parsed user dict on success,
    or None if the signature is missing/invalid."""
    import hashlib
    import hmac
    import json
    from urllib.parse import parse_qsl

    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed_hash, received_hash):
            return None
        user_json = parsed.get("user")
        return json.loads(user_json) if user_json else None
    except Exception:
        return None


def warranty_status(approved_at, warranty_days):
    """Human-readable Khmer warranty countdown for an approved order.
    Returns None if the item has no warranty (warranty_days=0) or the order isn't approved yet."""
    if not approved_at or not warranty_days:
        return None
    try:
        approved = datetime.strptime(approved_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    expires = approved + timedelta(days=warranty_days)
    remaining = (expires - datetime.utcnow()).days
    if remaining < 0:
        return f"❌ Warranty ផុតកំណត់ (ផុតកាលពី {expires.strftime('%d/%m/%Y')})"
    return f"🛡️ Warranty នៅសល់ {remaining} ថ្ងៃ (ផុតកំណត់ {expires.strftime('%d/%m/%Y')})"


def pick_weighted_spin(pool):
    """pool: list of rows with 'name' and 'weight'. Picks one item, probability proportional
    to its weight relative to the total (weights don't need to sum to 100 - they're normalized)."""
    if not pool:
        return None
    total = sum(row["weight"] for row in pool)
    if total <= 0:
        return None
    r = random.uniform(0, total)
    upto = 0
    for row in pool:
        upto += row["weight"]
        if upto >= r:
            return row
    return pool[-1]  # floating point safety net
