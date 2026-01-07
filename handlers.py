from enum import Enum, auto
import random
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, Update, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, CommandHandler, ConversationHandler

from db import engine
from mappings import ChatRole, Game, GameChat, Card, CardType, TeamCardJoin, CardState, TaskCard, TaskSpecial, \
    PowerupCard
from utils import CheckFailedError, select_card_keyboard_markup, enum_callback_pattern, get_chat, \
    get_chat_id, get_game, \
    get_running_team_chat, \
    graceful_fail, \
    admin_get_game, show_tasks, \
    to_started_game, no_callback_graceful_fail, show_powerups, select_card, add_points


# --- General handlers ---
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _ = await context.bot.send_message(
        get_chat_id(update), "Welcome to TrainWreck! Type /help for a list of commands.",
    )


async def rules_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        rule_cards = session.scalars(
            select(Card).where(Card.card_type == CardType.RULE),
        ).all()

        for rule_card in rule_cards:
            _ = await context.bot.send_photo(
                get_chat_id(update), rule_card.image_path,
            )


# TODO
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Available commands:\n"
        "/help - Lists all available commands\n"
        "/create_team <team_number> - Assigns this chat to the chosen team number, only works if team does not already exist\n"
        "/rules - Displays the game rule cards\n"
        "/current_task - Shows the current task card for your team\n"
        "/show_powerups - Displays your team's current powerup cards\n"
        "/use_powerup - Displays your team's current powerup cards and allows you to choose one to use\n"
        "/complete_task - Marks the current task as complete and starts a new draw\n\n"
        "/admin_chat <password> - Sets this chat as the admin chat (requires password)\n"
        "/location_chat - Sets this chat as the location chat\n"
    )

    with Session(engine) as session:
        try:
            chat = get_chat(session, update)
            if chat.game.admin_chat.chat_id == chat.chat_id:
                help_text += (
                    "\nAdmin commands:\n"
                    "/delete_team <team_number> - Deletes the specified team chat assignment\n"
                    "/delete_admin_chat - Deletes the admin chat assignment"
                    "/delete_location_chat - Deletes the location chat assignment\n"
                    "/catch - Marks a catch as having occurred in the game and updates teams' roles. Once all teams are ready, restart the game by running /restart_game\n"
                    "/start_game - Starts the game for all teams\n"
                    "/restart_game - Restarts the game for all teams after a catch\n"
                    "/end_game - Ends the game for all teams, can be undone by calling /start_game\n"
                    "/reset_game - Resets the game state entirely, cannot be undone\n"
                )
        except CheckFailedError:
            pass

        _ = await context.bot.send_message(chat_id=get_chat_id(update), text=help_text)


@graceful_fail
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    with Session(engine) as session:
        chat = get_chat(session, update)
        chat_id = chat.chat_id

        if chat.callback_message_id is None:
            _ = await context.bot.send_message(
                chat_id, "No operation to cancel",
            )
            return ConversationHandler.END

        _ = await context.bot.edit_message_reply_markup(
            chat_id, chat.callback_message_id, reply_markup=None,
        )
        _ = await context.bot.send_message(
            chat_id, "Operation cancelled",
        )
        chat.callback_message_id = None

        session.commit()

        return ConversationHandler.END


# --- Creating teams ---
@no_callback_graceful_fail
async def create_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        while True:
            game_id = random.randint(100000, 999999)
            if session.get(Game, game_id) is None:
                break

        chat_id = get_chat_id(update)

        session.add(Game(game_id=game_id))
        session.flush()
        session.add(GameChat(chat_id=chat_id, game_id=game_id, role=ChatRole.ADMIN))
        session.commit()

        _ = await context.bot.send_message(
            chat_id,
            (
                f"New game created with game id: {game_id}, this chat is the admin chat of the game\n\n"
                "Use this id to set the team and location chats via /create_team_<team number> and /create_location_chat"
            ),
        )


def create_team_handler_generator(team_num: Literal[1, 2, 3]):
    @no_callback_graceful_fail
    async def create_team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        with Session(engine) as session:
            game = get_game(session, context)
            if getattr(game, f"team_{team_num}_chat") is not None:
                raise CheckFailedError(
                    f"Team chat already exists, choose another team number or ask your admin to delete team {team_num}'s chat",
                )

            chat_id = get_chat_id(update)
            team_chat = GameChat(chat_id=chat_id, game_id=game.game_id, role=ChatRole(f"team_{team_num}"))
            session.add(team_chat)
            session.flush()

            cards = session.scalars(select(Card).where(Card.card_type != CardType.RULE)).all()
            for card in cards:
                session.add(
                    TeamCardJoin(
                        team_chat_id=team_chat.chat_id,
                        card_id=card.card_id,
                        state=CardState.UNDRAWN,
                    ),
                )
            session.commit()

        _ = await context.bot.send_message(
            chat_id,
            f"This chat has been assigned to team {team_num}",
        )

    return create_team_handler


@no_callback_graceful_fail
async def create_location_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        game = get_game(session, context)
        if game.location_chat is not None:
            raise CheckFailedError(
                f"Location chat already exists, choose another team number or ask your admin to delete the location chat",
            )

        chat_id = get_chat_id(update)
        location_chat = GameChat(chat_id=chat_id, game_id=game.game_id, role=ChatRole.LOCATION)
        session.add(location_chat)
        session.commit()

        _ = await context.bot.send_message(
            chat_id,
            f"This chat has been assigned as the location chat",
        )


# --- Deleting chats (admin only) ---
@no_callback_graceful_fail
async def delete_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        game = admin_get_game(session, update)
        session.delete(game)
        session.commit()

        _ = await context.bot.send_message(
            get_chat_id(update),
            "Game successfully deleted, all chats have been unassigned",
        )


def delete_team_handler_generator(team_num: Literal[1, 2, 3]):
    @no_callback_graceful_fail
    async def delete_team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        with Session(engine) as session:
            game = admin_get_game(session, update)
            team_chat: GameChat | None = cast(GameChat | None, getattr(game, f"team_{team_num}_chat"))
            if team_chat is None:
                raise CheckFailedError(f"Team {team_num} chat does not exist, cannot delete")
            else:
                session.delete(team_chat)
                session.commit()

            _ = await context.bot.send_message(
                get_chat_id(update),
                f"Team {team_num} chat successfully deleted, team can now create a new chat assignment",
            )

    return delete_team_handler


@no_callback_graceful_fail
async def delete_location_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        game = admin_get_game(session, update)
        location_chat: GameChat | None = game.location_chat
        if location_chat is None:
            raise CheckFailedError(f"Location chat does not exist, cannot delete")
        else:
            session.delete(location_chat)
            session.commit()

        _ = await context.bot.send_message(
            get_chat_id(update),
            f"Location chat successfully deleted, a new location chat can now be created",
        )


# --- Starting and ending games ---
class StartCycleStates(Enum):
    DRAWING_TASKS = auto()


class StartCycleActions(Enum):
    SELECT_TASK = auto()


async def _start_cycle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        game = to_started_game(admin_get_game(session, update))
        running_chat_id = game.running_team_chat.chat_id
        for team_num in range(1, 4):
            team_chat: GameChat = cast(GameChat, getattr(game, f"team_{team_num}_chat"))
            if team_chat.chat_id == running_chat_id:
                text = "The game has started! You are the runners, please send your location into the location chat"
            else:
                text = "The game has started! You are the chasers, please wait 20 minutes before starting your chase"
            _ = await context.bot.send_message(team_chat.chat_id, text)

        for task in show_tasks(session, running_chat_id, 3):
            _ = await context.bot.send_photo(running_chat_id, task.image_path)

        keyboard_markup = select_card_keyboard_markup(
            session, running_chat_id, TaskCard, StartCycleActions.SELECT_TASK
        )
        callback_message = await context.bot.send_message(
            running_chat_id, "Select your task:", reply_markup=keyboard_markup,
        )
        game.running_team_chat.callback_message_id = callback_message.message_id

        session.commit()


@no_callback_graceful_fail
async def start_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with (Session(engine) as session):
        game = admin_get_game(session, update)
        if game.is_started:
            raise CheckFailedError("Game is already started")

        missing_chats: list[str] = []
        if game.location_chat is None:
            missing_chats.append("location")
        if game.team_1_chat is None:
            missing_chats.append("team_1")
        if game.team_2_chat is None:
            missing_chats.append("team_2")
        if game.team_3_chat is None:
            missing_chats.append("team_3")

        if len(missing_chats) > 0:
            raise CheckFailedError(f"Missing required chats: {', '.join(missing_chats)}")

        game.running_team_chat_id = cast(GameChat, game.team_1_chat).chat_id
        session.flush()

        game.is_started = True
        session.commit()

        await _start_cycle(update, context)


@no_callback_graceful_fail
async def end_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        game = admin_get_game(session, update)
        if not game.is_started:
            raise CheckFailedError("Game is not started")

        game.is_started = False
        session.commit()

        _ = await context.bot.send_message(
            get_chat_id(update),
            "Game successfully ended, teams can now wait for the next game or ask their admin to restart the game",
        )


@no_callback_graceful_fail
async def catch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        game = admin_get_game(session, update)
        started_game = to_started_game(game)
        if started_game.is_paused:
            raise CheckFailedError("Game is currently paused, cannot register catch")

        running_team_chat = started_game.running_team_chat
        if running_team_chat.callback_message_id is not None:
            _ = await context.bot.edit_message_reply_markup(
                get_chat_id(update), running_team_chat.callback_message_id, reply_markup=None,
            )

        for team_card_join in running_team_chat.team_card_joins:
            if team_card_join.state == CardState.SHOWN:
                team_card_join.state = CardState.UNDRAWN
            elif team_card_join.state == CardState.DRAWN:
                team_card_join.state = CardState.USED

        running_team_num = int(running_team_chat.role.value.split("_")[-1])
        new_running_team_chat = cast(GameChat, getattr(started_game, f"team_{(running_team_num + 1) % 3}_chat"))
        game.running_team_chat_id = new_running_team_chat.chat_id

        game.is_paused = True
        game.all_or_nothing_active = False
        game.buy_1_get_1_free_active = False
        session.commit()

        _ = await context.bot.send_message(
            get_chat_id(update),
            "Catch registered, the next team is now the running team. Use /restart_game to start the next cycle.",
        )


@no_callback_graceful_fail
async def restart_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        game = admin_get_game(session, update)
        started_game = to_started_game(game)
        if not started_game.is_paused:
            raise CheckFailedError("Game is not paused, cannot restart game")

        game.is_paused = False
        session.commit()

        await _start_cycle(update, context)


@graceful_fail
async def select_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        selected_task = await select_card(session, update, context, TaskCard)

        _ = await context.bot.send_message(get_chat_id(update), "You have selected the following task:")
        _ = await context.bot.send_photo(get_chat_id(update), selected_task.image_path)

        session.commit()

    return ConversationHandler.END


# --- Complete task handlers ---
class CompleteTaskActions(Enum):
    REVEAL_TASKS_OR_POWERUPS = auto()
    SELECT_TASK = auto()
    SELECT_POWERUP = auto()
    FULLERTON = auto()
    B1G1F = auto()
    DREW_B1G1F = auto()

@no_callback_graceful_fail
async def complete_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass


# --- Setting handlers ---
def set_handlers(application: Application[Any, Any, Any, Any, Any, Any]) -> None:  # pyright: ignore [reportExplicitAny]
    handlers = [
        CommandHandler("start", start_handler),
        CommandHandler("help", help_handler),
        CommandHandler("cancel", cancel_handler),

        CommandHandler("create_game", create_game_handler),
        CommandHandler("create_team_1", create_team_handler_generator(1)),
        CommandHandler("create_team_2", create_team_handler_generator(2)),
        CommandHandler("create_team_3", create_team_handler_generator(3)),
        CommandHandler("create_location_chat", create_location_chat_handler),

        CommandHandler("delete_game", delete_game_handler),
        CommandHandler("delete_team_1", delete_team_handler_generator(1)),
        CommandHandler("delete_team_2", delete_team_handler_generator(2)),
        CommandHandler("delete_team_3", delete_team_handler_generator(3)),
        CommandHandler("delete_location_chat", delete_location_chat_handler),

        CommandHandler("end_game", end_game_handler),
        CommandHandler("catch", catch_handler),

        CommandHandler("start_game", start_game_handler),
        CommandHandler("restart_game", restart_game_handler),
        CallbackQueryHandler(select_task_handler, enum_callback_pattern(StartCycleActions.SELECT_TASK)),
    ]

    application.add_handlers(handlers)
