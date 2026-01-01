# --- Decorator and checks to guard functions ---
import re
from collections.abc import Callable
from functools import wraps
from typing import Coroutine, Any, Awaitable, TypeVar

from telegram import Update
from telegram.ext import ContextTypes

from common import games, chat_id_to_team, is_admin_chat, is_location_chat, \
    chat_id_to_chat, chat_id_to_game

OutT = TypeVar("OutT")
HandlerType = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, OutT | None]]
def guard[T](*checks: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[bool]]) -> Callable[[HandlerType], HandlerType]:
    def decorator(func: HandlerType) -> HandlerType:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> T | None:
            for check in checks:
                if not await check(update, context):
                    return None
            return await func(update, context)
        return wrapper
    return decorator

# --- General checks ---
async def no_callback_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = chat_id_to_chat(update.effective_chat.id)
    if chat is None:
        return True

    if chat.callback_message is not None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Finish the current operation or run /cancel")
        return False

    return True

async def valid_game_id_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if len(context.args) != 1 or (re.fullmatch(r"\d{6}", context.args[0]) is None):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a valid game id")
        return False

    game_id = int(context.args[0])
    if game_id not in games:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Game not found. Please check the game id and try again",
        )
        return False

    return True

async def game_not_started_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    game = chat_id_to_game(update.effective_chat.id)
    if game.game_state.is_started:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="The game has already started")
        return False

    return True

async def game_is_started_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    game = chat_id_to_game(update.effective_chat.id)
    if not game.game_state.is_started:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="The game has not yet started")
        return False

    return True

async def game_not_paused_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    game = chat_id_to_game(update.effective_chat.id)
    if game.game_state.is_paused:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="The game is currently paused")
        return False

    return True

async def game_is_paused_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    game = chat_id_to_game(update.effective_chat.id)
    if not game.game_state.is_paused:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="The game is currently running")
        return False

    return True


# --- Chat type (admin, team, location) checks ---
async def is_admin_chat_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not is_admin_chat(update.effective_chat.id):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="This chat is not an admin chat")
        return False

    return True

async def is_runner_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    team = chat_id_to_team(update.effective_chat.id)
    if team is None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="This chat is not a team chat")
        return False

    game = chat_id_to_game(update.effective_chat.id)
    if team != game.game_state.running_team:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You are not currently running")
        return False

    return True


# --- Checks for whether chats have been assigned ---
async def chat_not_assigned_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    assigned_type = None
    if chat_id_to_team(update.effective_chat.id) is not None:
        assigned_type = "team"
    elif is_admin_chat(update.effective_chat.id):
        assigned_type = "admin"
    elif is_location_chat(update.effective_chat.id):
        assigned_type = "location"

    if assigned_type is not None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"This chat is already assigned as a {assigned_type} chat",
        )
        return False

    return True

def team_chat_is_assigned_check(team_index: int) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[bool]]:
    async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        game = chat_id_to_game(update.effective_chat.id)
        if game is None:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="This chat is not associated with a game",
            )
            return False

        if game.teams[team_index] is None:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text=f"Team {team_index + 1} has not yet been assigned to a chat",
            )
            return False

        return True

    return check

async def location_chat_is_assigned_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    game = chat_id_to_game(update.effective_chat.id)
    if game is None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="This chat is not associated with a game",
        )
        return False

    if game.location_chat is None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="The location chat has not yet been assigned",
        )
        return False

    return True

async def chats_all_assigned_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    all_assigned = True
    for team_index in range(3):
        check = team_chat_is_assigned_check(team_index)
        all_assigned = all_assigned and await check(update, context)
    all_assigned = all_assigned and await location_chat_is_assigned_check(update, context)
    return all_assigned