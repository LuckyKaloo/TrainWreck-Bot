import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import ApplicationBuilder, AIORateLimiter, ContextTypes, ExtBot, Application, JobQueue

from handlers import set_handlers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING,
)

type ApplicationType = Application[ExtBot[int], ContextTypes.DEFAULT_TYPE, dict[Any, Any], dict[Any, Any], dict[Any, Any], JobQueue[ContextTypes.DEFAULT_TYPE]]  # pyright: ignore[reportExplicitAny]
async def set_bot_commands(application: ApplicationType):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Lists all available commands"),
        BotCommand("rules", "Shows the game rules"),
        BotCommand("create_game", "Creates a new game and assigns this chat as the admin chat"),
        BotCommand("create_team_1", "Assigns this chat as team 1's chat"),
        BotCommand("create_team_2", "Assigns this chat as team 2's chat"),
        BotCommand("create_team_3", "Assigns this chat as team 3's chat"),
        BotCommand("create_location_chat", "Assigns this chat as the location chat"),
        BotCommand("current_task", "Shows the currently drawn tasks"),
        BotCommand("show_powerups", "Shows the currently drawn powerups"),
        BotCommand("complete_task", "Marks a drawn task as completed and draws new tasks/powerups"),
        BotCommand("use_powerup", "Initiates the use of a powerup"),
        BotCommand("delete_game", "Deletes the game and unassigns all chats"),
        BotCommand("delete_team_1", "Deletes team 1's chat assignment"),
        BotCommand("delete_team_2", "Deletes team 2's chat assignment"),
        BotCommand("delete_team_3", "Deletes team 3's chat assignment"),
        BotCommand("delete_location_chat", "Deletes the location chat assignment"),
        BotCommand("start_game", "Starts the game for all teams"),
        BotCommand("end_game", "Ends the game for all teams"),
        BotCommand("catch", "Marks a catch as having occurred in the game"),
        BotCommand("restart_game", "Restarts the game after a catch has occurred"),
    ]
    _ = await application.bot.set_my_commands(commands)

def main():
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
    application.post_init = set_bot_commands

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

if __name__ == '__main__':
    main()
