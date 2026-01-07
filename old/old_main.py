import logging
import os

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, AIORateLimiter

from old_handlers import set_handlers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

if __name__ == '__main__':
    load_dotenv()

    application = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).rate_limiter(AIORateLimiter(overall_max_rate=1, max_retries=1)).build()

    set_handlers(application)

    application.run_polling()