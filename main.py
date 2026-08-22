"""
ដំណើរការ Bot (Admin + Store, Helper ប្រសិនបើកំណត់ Token) + Mini App Web Server ក្នុងពេលតែមួយ។
ដំណើរការ: python main.py
ឈប់: Ctrl + C
"""
import asyncio
import logging
import os
from threading import Thread

import database as db
import admin_bot
import store_bot
from keep_alive import keep_alive

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def start_webapp_server():
    import webapp_server
    port = int(os.getenv("WEBAPP_PORT", os.getenv("PORT", "8080")))
    logger.info(f"Starting Mini App web server on port {port}")
    Thread(target=webapp_server.run, kwargs={"port": port}, daemon=True).start()


def run_bot_polling(build_app_func, bot_name):
    """Run a bot in a dedicated asyncio event loop (separate thread)"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_bot_async(build_app_func, bot_name))
    except Exception as e:
        logger.error(f"{bot_name} error: {e}")
    finally:
        loop.close()


async def _run_bot_async(build_app_func, bot_name):
    """Initialize, start, and poll a bot in its own event loop"""
    app = build_app_func()
    try:
        await app.initialize()
        await app.start()
        logger.info(f"{bot_name} initialized and started")
        await app.updater.start_polling()
    except Exception as e:
        logger.error(f"{bot_name} polling failed: {e}")
        raise
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


async def main():
    db.init_db()

    # Mini App web server (serves the store UI + product API). Runs whenever WEBAPP_URL
    # is configured, since that means the person wants the Mini App available.
    if os.getenv("WEBAPP_URL"):
        start_webapp_server()
    elif os.getenv("ENABLE_KEEPALIVE") == "1":
        keep_alive()

    bots = [
        ("Admin Bot", admin_bot.build_app),
        ("Store Bot", store_bot.build_app),
    ]

    # Helper Bot (Blox Fruits tips bot) is optional - only starts if a real token is set
    helper_token = os.getenv("HELPER_BOT_TOKEN", "")
    if helper_token and "PUT_YOUR" not in helper_token:
        import helper_bot
        bots.append(("Helper Bot", helper_bot.build_app))

    # Start each bot's polling in a separate thread
    polling_threads = []
    for bot_name, build_app_func in bots:
        thread = Thread(
            target=run_bot_polling,
            args=(build_app_func, bot_name),
            daemon=True,
            name=f"{bot_name}-polling"
        )
        thread.start()
        polling_threads.append(thread)

    logger.info(f"{len(bots)} bot(s) running in separate polling threads. Press Ctrl+C to stop.")

    # Keep the main thread alive
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())

