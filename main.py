import logging
import os

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, AIORateLimiter

from handlers import set_handlers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING,
)

if __name__ == '__main__':
    if not load_dotenv():
        raise RuntimeError('No .env found.')

    bot_token = os.getenv("BOT_TOKEN")
    if bot_token is None:
        raise RuntimeError("Bot token not defined in .env")

    application = (
        ApplicationBuilder()
        .token(bot_token)
        .rate_limiter(AIORateLimiter(overall_max_rate=1, max_retries=1))
        .build()
    )

    set_handlers(application)

    application.run_polling()
