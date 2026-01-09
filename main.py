import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import ApplicationBuilder, AIORateLimiter

from handlers import set_handlers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING,
)

if __name__ == '__main__':
    _ = load_dotenv()

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

    # command_names = [
    #     "/start", "/help",
    #     "/create_game", "/create_team_1", "/create_team_2", "/create_team_3", "/create_location_chat",
    #     "/delete_game", "/delete_team_1", "/delete_team_2", "/delete_team_3", "/delete_location_chat",
    #     "/start_game", "/end_game", "/catch", ";restart_game",
    #     "/complete_task",
    #     "/current_task", "/show_powerups", "/use_powerup",
    # ]
    # commands = [BotCommand(name, "") for name in command_names]
    # await application.bot.set_my_commands(commands)
    #
    application.run_polling()
