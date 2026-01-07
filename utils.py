from enum import Enum
import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import cast

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardButton, CallbackQuery, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db import engine
from mappings import ChatRole, PowerupCard, TaskSpecial, TaskType, TaskCard, PowerupSpecial, RuleCard, GameChat, Game, \
    TeamCardJoin, CardState

# --- Loading cards ---
#TODO store in json lol
_POWERUP_SEND_TO_CHASERS_IDS = [1, 2, 3, 4, 5, 8, 9]
_TASK_ID_TO_SPECIAL = {
    35: TaskSpecial.FULLERTON,
    39: TaskSpecial.MBS
}
_POWERUP_ID_TO_SPECIAL = {
    6: PowerupSpecial.ALL_OR_NOTHING,
    7: PowerupSpecial.BUY_1_GET_1_FREE,
}

all_tasks = []
all_powerups = []
all_rules = []

def _make_cards(root_path: Path) -> None:
    """
    Loads cards from the given directory into the database.

    :param root_path: Path to the directory containing card images
    :return:
    """
    with Session(engine) as session:
        for card_path in sorted(root_path.iterdir()):
            if not card_path.is_file():
                continue

            card_info = card_path.stem.split(" ")
            if card_info[0] == "Location":
                if card_info[1] == "N":
                    task_type = TaskType.NORMAL
                elif card_info[1] == "E":
                    task_type = TaskType.EXTREME
                else:
                    print(f"are you stupid {card_path} is wrong")
                    continue

                session.add(TaskCard(
                    image_path=str(card_path),
                    task_type=task_type,
                    task_special=_TASK_ID_TO_SPECIAL.get(int(card_info[2]), TaskSpecial.NONE),
                ))
            elif card_info[0] == "Powerup":
                session.add(PowerupCard(
                    image_path=str(card_path),
                    powerup_send_to_chasers=int(card_info[1]) in _POWERUP_SEND_TO_CHASERS_IDS,
                    powerup_special=_POWERUP_ID_TO_SPECIAL.get(int(card_info[1]), PowerupSpecial.NONE),
                ))
            elif card_info[0] == "Info":
                session.add(RuleCard(
                    image_path=str(card_path)
                ))

        session.commit()

_make_cards(Path("cards"))


# --- StartedGame convenience class ---
@dataclass
class StartedGame:
    game_id: int
    admin_chat: GameChat
    location_chat: GameChat
    team_1_chat: GameChat
    team_2_chat: GameChat
    team_3_chat: GameChat
    running_team_chat: GameChat

    is_paused: bool
    all_or_nothing: bool
    buy_1_get_1_free: bool

# --- Checks ---
class CheckFailedError(Exception):
    pass

type HandlerType[OutT] = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[None, None, OutT]]
def graceful_fail[T](f: HandlerType[T]) -> HandlerType[T | None]:
    """
    Decorator to catch CheckFailedError exceptions and send the error message to the user.
    """

    @wraps(f)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> T | None:
        try:
            return await f(update, context)
        except CheckFailedError as e:
            _ = await context.bot.send_message(get_chat_id(update), str(e))

    return wrapper

def no_callback_check(update: Update):
    """
    Check if there is an ongoing callback operation in the chat.
    """
    with Session(engine) as session:
        chat: GameChat | None = None
        try:
            chat = get_chat(session, update)
        except CheckFailedError:
            pass

        if chat is not None and chat.callback_message_id is not None:
            raise CheckFailedError("Finish or cancel the current callback operation first")

def no_callback_graceful_fail[T](f: HandlerType[T]) -> HandlerType[T | None]:
    """
    Decorator to check that the chat has no ongoing callbacks,
    catch CheckFailedError exceptions and send the error message to the user.
    """
    @wraps(f)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> T | None:
        try:
            no_callback_check(update)
            return await f(update, context)
        except CheckFailedError as e:
            _ = await context.bot.send_message(get_chat_id(update), str(e))

    return wrapper


# --- Database helper functions ---
def get_chat_id(update: Update) -> int:
    """
    Gets the chat ID from the update, throws RuntimeError if the update has no effective chat.
    """
    if update.effective_chat is None:
        raise RuntimeError("Update has no effective chat")
    return update.effective_chat.id

def get_chat(session: Session, update: Update) -> GameChat:
    """
    Gets the GameChat associated with the chat in the update,
    raises CheckFailedError if there is no GameChat associated with the update.
    """
    chat: GameChat | None = session.get(GameChat, get_chat_id(update))
    if chat is None:
        raise CheckFailedError("Chat is not assigned to any role")
    return chat

def get_game(session: Session, context: ContextTypes.DEFAULT_TYPE) -> Game:
    """
    Gets the GameChat associated with the chat in the update,
    raises CheckFailedError if there is no GameChat associated with the update.
    """
    if context.args is None or len(context.args) != 1 or (re.fullmatch(r"\d{6}", context.args[0]) is None):
        raise CheckFailedError("Please provide a valid game id")

    game_id = int(context.args[0])
    game: Game | None = session.get(Game, game_id)
    if game is None:
        raise CheckFailedError("Game not found, please check the game id and try again")

    return game

def admin_get_game(session: Session, update: Update) -> Game:
    """
    Gets the Game associated with the admin chat in the update,
    raises CheckFailedError if the chat is not an admin chat.
    """
    chat = get_chat(session, update)
    game = chat.game
    if chat.chat_id != game.admin_chat.chat_id:
        raise CheckFailedError("This is not an admin chat")

    return game

def to_started_game(game: Game) -> StartedGame:
    """
    Converts a Game to a StartedGame, raises CheckFailedError if the game is not started.

    StartedGame is a convenience class that guarantees that all necessary chats for a game are not None,
    to help with type checking
    """
    if not game.is_started:
        raise CheckFailedError("Game is not started, please wait for your admin to start the game")

    assert game.location_chat is not None
    assert game.team_1_chat is not None
    assert game.team_2_chat is not None
    assert game.team_3_chat is not None
    assert game.running_team_chat is not None

    return StartedGame(
        game_id=game.game_id,
        admin_chat=game.admin_chat,
        location_chat=game.location_chat,
        team_1_chat=game.team_1_chat,
        team_2_chat=game.team_2_chat,
        team_3_chat=game.team_3_chat,
        running_team_chat=game.running_team_chat,
        is_paused=game.is_paused,
        all_or_nothing=game.all_or_nothing_active,
        buy_1_get_1_free=game.buy_1_get_1_free_active,
    )


# --- Enum formatter ---
def format_enum_callback(enum_value: Enum) -> str:
    """
    Formats an enum value into a string suitable for use as a callback data prefix.
    """
    enum_class_name = enum_value.__class__.__name__
    class_name_snake = ''.join(['_' + c.lower() if c.isupper() else c for c in enum_class_name]).lstrip('_')
    member_name_lower = enum_value.name.lower()
    return f"{class_name_snake}:{member_name_lower}"

def enum_callback_pattern(enum_value: Enum) -> str:
    """
    Returns a regex pattern string to match callback data for the given enum value.
    """
    return f"^{format_enum_callback(enum_value)}"


# --- Drawing cards helper functions ---
def get_running_team_chat(session: Session, update: Update) -> GameChat:
    """
    Returns the GameChat associated with the update if it is a team chat and the team is currently running,
    raises CheckFailedError otherwise.
    """
    chat_id = get_chat_id(update)
    chat: GameChat | None = session.get(GameChat, chat_id)
    if chat is None or chat.role not in [ChatRole.TEAM_1, ChatRole.TEAM_2, ChatRole.TEAM_3]:
        raise CheckFailedError("This chat is not a team chat")

    if chat.game.running_team_chat_id != chat.chat_id:
        raise CheckFailedError("Your team is not currently running")

    return chat

def _show_cards_query[T: (TaskCard, PowerupCard)](chat_id: int, card_type: type[T]) -> Select[tuple[T, TeamCardJoin]]:
    """
    Returns a query to select undrawn cards of the given type for the given chat ID.
    """
    return (
        select(card_type, TeamCardJoin)
        .join(TeamCardJoin, TeamCardJoin.card_id == card_type.card_id)
        .where(
            TeamCardJoin.team_chat_id == chat_id,
            TeamCardJoin.state == CardState.UNDRAWN,
        )
    )

def _execute_show_cards_query[T: (TaskCard, PowerupCard)](
    session: Session, query: Select[tuple[T, TeamCardJoin]], num_cards: int
) -> list[T]:
    """
    Executes the given query to select cards, updates their states to SHOWN, and returns the shown cards.
    """
    result = session.execute(
        query.order_by(func.random()).limit(num_cards)
    )

    shown_cards: list[T] = []
    for row in result:
        card, team_card_join = row.tuple()
        team_card_join.state = CardState.SHOWN
        shown_cards.append(card)

    if len(shown_cards) < num_cards:
        raise CheckFailedError("Not enough tasks left to show")

    return shown_cards

def show_tasks(session: Session, chat_id: int, num_cards: int, extremes_only: bool = False) -> list[TaskCard]:
    """
    Sets num_cards randomly selected undrawn tasks to SHOWN state and returns them,
    if extremes_only is True then only extreme tasks can be shown.
    """
    query = _show_cards_query(chat_id, TaskCard)
    if extremes_only:
        query = (
            query
            .where(TaskCard.task_type == TaskType.EXTREME)
        )
    return _execute_show_cards_query(session, query, num_cards)

def show_powerups(session: Session, chat_id: int, num_cards: int) -> list[PowerupCard]:
    """
    Sets num_cards randomly selected undrawn powerups to SHOWN state and returns them.
    """
    query = _show_cards_query(chat_id, PowerupCard)
    return _execute_show_cards_query(session, query, num_cards)

async def select_card[T: (TaskCard, PowerupCard)](
    session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, card_type: type[T]
) -> T:
    """
    Selects a card based on the callback query data, clears the callback message and returns the selected card.
    """
    query = cast(CallbackQuery, update.callback_query)
    _ = await query.answer()

    chat = get_chat(session, update)
    if chat.callback_message_id is not None:
        _ = await context.bot.edit_message_reply_markup(
            get_chat_id(update), chat.callback_message_id, reply_markup=None,
        )

    card_id = int(cast(str, query.data).split(":")[-1])
    return db_select_card(session, update, card_id, card_type)

def db_select_card[T: (TaskCard, PowerupCard)](session: Session, update: Update, card_id: int, card_type: type[T]) -> T:
    """
    Sets the selected card to DRAWN state and all other SHOWN cards to UNDRAWN state, returns the selected card.
    """
    chat = get_running_team_chat(session, update)

    result = session.execute(
        select(card_type, TeamCardJoin)
        .join(TeamCardJoin, TeamCardJoin.card_id == card_type.card_id)
        .where(
            TeamCardJoin.team_chat_id == chat.chat_id,
            TeamCardJoin.state == CardState.SHOWN,
        )
    ).all()

    selected_card: T | None = None
    for row in result:
        card, team_card_join = row.tuple()
        if card.card_id != card_id:
            team_card_join.state = CardState.UNDRAWN
        else:
            team_card_join.state = CardState.DRAWN
            selected_card = card

    assert selected_card is not None
    return selected_card

def select_card_keyboard_markup[T: (TaskCard, PowerupCard)](
    session: Session, chat_id: int, card_type: type[T], enum_value: Enum
) -> InlineKeyboardMarkup:
    """
    Returns an inline keyboard for selecting a shown card of the given type for the given chat ID.
    """
    shown_tasks = session.execute(
        select(card_type)
        .join(TeamCardJoin, card_type.card_id == TeamCardJoin.card_id)
        .where(
            TeamCardJoin.state == CardState.SHOWN,
            TeamCardJoin.team_chat_id == chat_id,
        ),
    ).scalars().all()

    keyboard = [[InlineKeyboardButton(
        f"Task {task_index + 1}",
        callback_data=f"{format_enum_callback(enum_value)}:{task.card_id}",
    )] for task_index, task in enumerate(shown_tasks)]

    return InlineKeyboardMarkup(keyboard)

def add_points(team_chat: GameChat, task: TaskCard):
    if team_chat.score is None:
        raise RuntimeError("Team chat has no score")

    if task.task_type == TaskType.NORMAL:
        team_chat.score += 2
    elif task.task_type == TaskType.EXTREME:
        team_chat.score += 3