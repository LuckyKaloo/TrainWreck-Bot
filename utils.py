import re
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db import engine
from mappings import B1G1FStates, Card, ChatRole, PowerupCard, TaskSpecial, TaskType, TaskCard, PowerupSpecial, \
    RuleCard, GameChat, \
    Game, \
    TeamCardJoin, CardState

# --- Loading cards ---
_POWERUP_DO_NOT_SEND_NAMES = ["All or Nothing", "Buy 1 Get 1 Free"]
_TASK_NAME_TO_SPECIAL = {
    "Pair O' Legs Error": TaskSpecial.FULLERTON,
    "Let's Go Gambling!": TaskSpecial.MBS
}
_POWERUP_ID_TO_SPECIAL = {
    "All or Nothing": PowerupSpecial.ALL_OR_NOTHING,
    "Buy 1 Get 1 Free": PowerupSpecial.BUY_1_GET_1_FREE,
}

all_tasks = []
all_powerups = []
all_rules = []


def _load_cards_into_db(root_path: Path) -> None:
    with Session(engine) as session:
        for rule_path in sorted((root_path / "rules").iterdir()):
            if not rule_path.is_file():
                continue

            session.add(RuleCard(
                title=rule_path.stem,
                image_path=str(rule_path),
            ))

        for task_path in sorted((root_path / "tasks").iterdir()):
            if not task_path.is_file():
                continue

            card_info = task_path.stem.split("_")
            if card_info[1] == "N":
                task_type = TaskType.NORMAL
            elif card_info[1] == "E":
                task_type = TaskType.EXTREME
            else:
                print(f"are you stupid {task_path} is wrong")
                continue

            session.add(TaskCard(
                title=card_info[2],
                image_path=str(task_path),
                task_type=task_type,
                task_special=_TASK_NAME_TO_SPECIAL.get(card_info[2], TaskSpecial.NONE),
            ))

        for powerup_path in sorted((root_path / "powerups").iterdir()):
            if not powerup_path.is_file():
                continue

            card_info = powerup_path.stem.split("_")
            send_to_chasers = card_info[2] not in _POWERUP_DO_NOT_SEND_NAMES

            session.add(PowerupCard(
                title=card_info[2],
                image_path=str(powerup_path),
                powerup_send_to_chasers=send_to_chasers,
                powerup_special=_POWERUP_ID_TO_SPECIAL.get(card_info[2], PowerupSpecial.NONE),
            ))

        session.commit()


_load_cards_into_db(Path("cards"))


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
    B1G1F: B1G1FStates


# --- Checks ---
class CheckFailedError(Exception):
    pass


type HandlerType[OutT] = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[None, None, OutT]]


def graceful_fail[T](f: HandlerType[T]) -> HandlerType[T | None]:
    @wraps(f)
    async def wrapper(tele_update: Update, context: ContextTypes.DEFAULT_TYPE) -> T | None:
        print(f"Running handler {f.__name__}")

        try:
            return await f(tele_update, context)
        except CheckFailedError as e:
            _ = await context.bot.send_message(get_chat_id(tele_update), str(e))

    return wrapper

def no_callback[T](f: HandlerType[T]) -> HandlerType[T | None]:
    @wraps(f)
    async def wrapper(tele_update: Update, context: ContextTypes.DEFAULT_TYPE) -> T | None:
        with Session(engine) as session:
            chat: GameChat | None = None
            try:
                chat = get_game_chat_or_raise(session, tele_update)
            except CheckFailedError:
                pass

            if chat is not None and chat.callback_message_id is not None:
                raise CheckFailedError("Finish or cancel the current callback operation first")
        return await f(tele_update, context)

    return wrapper


# --- Helper functions ---
def get_chat_id(tele_update: Update) -> int:
    if tele_update.effective_chat is None:
        raise RuntimeError("Update has no effective chat")
    return tele_update.effective_chat.id


def get_game_chat_or_raise(session: Session, tele_update: Update) -> GameChat:
    chat: GameChat | None = session.get(GameChat, get_chat_id(tele_update))
    if chat is None:
        raise CheckFailedError("Chat is not assigned to any role")
    return chat


def validate_game_id(session: Session, context: ContextTypes.DEFAULT_TYPE) -> Game:
    if context.args is None or len(context.args) != 1 or (re.fullmatch(r"\d{6}", context.args[0]) is None):
        raise CheckFailedError("Please provide a valid game id")

    game_id = int(context.args[0])
    game: Game | None = session.get(Game, game_id)
    if game is None:
        raise CheckFailedError("Game not found, please check the game id and try again")

    return game


def ensure_admin_chat(session: Session, tele_update: Update) -> GameChat:
    chat = get_game_chat_or_raise(session, tele_update)
    if chat.role != ChatRole.ADMIN:
        raise CheckFailedError("This chat is not an admin chat")

    return chat


def ensure_running_team_chat(session: Session, tele_update: Update) -> GameChat:
    chat = get_game_chat_or_raise(session, tele_update)
    if chat.role not in [ChatRole.TEAM_1, ChatRole.TEAM_2, ChatRole.TEAM_3]:
        raise CheckFailedError("This chat is not a team chat")

    if chat.game.running_team_chat_id != chat.chat_id:
        raise CheckFailedError("Your team is not currently running")

    return chat


def to_started_game(game: Game) -> StartedGame:
    if not game.is_started:
        raise CheckFailedError("Game is not started, please wait for your admin to start the game")

    assert game.location_chat is not None, "SQL trigger failed to ensure location chat exists for started game"
    assert game.team_1_chat is not None, "SQL trigger failed to ensure team 1 chat exists for started game"
    assert game.team_2_chat is not None, "SQL trigger failed to ensure team 2 chat exists for started game"
    assert game.team_3_chat is not None, "SQL trigger failed to ensure team 3 chat exists for started game"
    assert game.running_team_chat is not None, "SQL trigger failed to ensure running team chat exists for started game"

    return StartedGame(
        game_id=game.game_id,
        admin_chat=game.admin_chat,
        location_chat=game.location_chat,
        team_1_chat=game.team_1_chat,
        team_2_chat=game.team_2_chat,
        team_3_chat=game.team_3_chat,
        running_team_chat=game.running_team_chat,
        is_paused=game.is_paused,
        all_or_nothing=game.all_or_nothing,
        B1G1F=game.B1G1F,
    )


def get_tasks(session: Session, chat_id: int, card_state: CardState) -> Sequence[TaskCard]:
    return session.scalars(
        select(TaskCard)
        .join(TeamCardJoin, TaskCard.card_id == TeamCardJoin.card_id)
        .where(
            TeamCardJoin.state == card_state,
            TeamCardJoin.team_chat_id == chat_id,
        ),
    ).all()


def get_powerups(session: Session, chat_id: int, card_state: CardState) -> Sequence[PowerupCard]:
    return session.scalars(
        select(PowerupCard)
        .join(TeamCardJoin, PowerupCard.card_id == TeamCardJoin.card_id)
        .where(
            TeamCardJoin.state == card_state,
            TeamCardJoin.team_chat_id == chat_id,
        ),
    ).all()


async def validate_callback_query(session: Session, tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = tele_update.callback_query
    if query is None:
        raise RuntimeError("Update has no callback query")
    _ = await query.answer()
    if query.data is None:
        raise RuntimeError("Callback query has no data")

    chat = ensure_running_team_chat(session, tele_update)
    if chat.callback_message_id is not None:
        _ = await context.bot.delete_message(chat.chat_id, chat.callback_message_id)
    chat.callback_message_id = None

    session.commit()

    return chat, query.data


# --- Enum formatter ---
def card_callback_generator(enum_value: Enum) -> str:
    """
    Converts Enum value to a callback data string in the format "enum_class_name:member_name".
    """
    enum_class_name = enum_value.__class__.__name__
    class_name_snake = ''.join(['_' + c.lower() if c.isupper() else c for c in enum_class_name]).lstrip('_')
    member_name_lower = enum_value.name.lower()
    return f"{class_name_snake}:{member_name_lower}"


def card_callback_pattern(enum_value: Enum) -> str:
    """
    Converts Enum value to regex matching callback data provided by card_callback_generator.
    """
    return f"^{card_callback_generator(enum_value)}"


# --- Drawing cards helper functions ---
def generate_shown_tasks(session: Session, chat_id: int, num_cards: int, extremes_only: bool) -> list[TaskCard]:
    query = (
        select(TaskCard, TeamCardJoin)
        .join(TeamCardJoin, TeamCardJoin.card_id == TaskCard.card_id)
        .where(
            TeamCardJoin.team_chat_id == chat_id,
            TeamCardJoin.state == CardState.UNDRAWN,
        )
    )
    if extremes_only:
        query = (
            query
            .where(TaskCard.task_type == TaskType.EXTREME)
        )
    result = session.execute(
        query.order_by(func.random()).limit(num_cards),
    )

    shown_cards: list[TaskCard] = []
    for row in result:
        card, team_card_join = row.tuple()
        team_card_join.state = CardState.SHOWN
        shown_cards.append(card)

    if len(shown_cards) < num_cards:
        raise CheckFailedError("Not enough tasks left to show")

    session.commit()

    return shown_cards


def generate_shown_powerups(session: Session, chat_id: int, num_cards: int) -> list[PowerupCard]:
    query = (
        select(PowerupCard, TeamCardJoin)
        .join(TeamCardJoin, TeamCardJoin.card_id == PowerupCard.card_id)
        .where(
            TeamCardJoin.team_chat_id == chat_id,
            TeamCardJoin.state == CardState.UNDRAWN,
        )
    )
    result = session.execute(
        query.order_by(func.random()).limit(num_cards),
    )

    shown_cards: list[PowerupCard] = []
    for row in result:
        card, team_card_join = row.tuple()
        team_card_join.state = CardState.SHOWN
        shown_cards.append(card)

    if len(shown_cards) < num_cards:
        raise CheckFailedError("Not enough powerups left to show")

    session.commit()

    return shown_cards


def db_select_card(session: Session, chat: GameChat, card_id: int, clear_shown: bool) -> Card:
    team_card_join = session.scalars(
        select(TeamCardJoin)
        .where(
            TeamCardJoin.card_id == card_id,
            TeamCardJoin.team_chat_id == chat.chat_id,
            TeamCardJoin.state == CardState.SHOWN,
        )
        .options(joinedload(TeamCardJoin.card)),
    ).one_or_none()
    if team_card_join is None:
        raise CheckFailedError("No card found with that ID")
    team_card_join.state = CardState.DRAWN

    if clear_shown:
        _ = session.execute(
            update(TeamCardJoin)
            .where(
                TeamCardJoin.team_chat_id == chat.chat_id,
                TeamCardJoin.state == CardState.SHOWN,
            )
            .values(state=CardState.UNDRAWN),
        )

    session.commit()

    return team_card_join.card


def create_shown_task_selector(session: Session, chat_id: int, enum_value: Enum) -> InlineKeyboardMarkup:
    shown_tasks = get_tasks(session, chat_id, CardState.SHOWN)

    return InlineKeyboardMarkup.from_column(
        [InlineKeyboardButton(
            task.title,
            callback_data=f"{card_callback_generator(enum_value)}:{task.card_id}",
        ) for task in shown_tasks],
    )


def create_shown_powerup_selector(session: Session, chat_id: int, enum_value: Enum) -> InlineKeyboardMarkup:
    shown_powerups = get_powerups(session, chat_id, CardState.SHOWN)

    return InlineKeyboardMarkup.from_column(
        [InlineKeyboardButton(
            powerup.title,
            callback_data=f"{card_callback_generator(enum_value)}:{powerup.card_id}",
        ) for powerup in shown_powerups],
    )


def add_points(team_chat: GameChat, task: TaskCard):
    if team_chat.score is None:
        raise RuntimeError("Team chat has no score")

    if task.task_type == TaskType.NORMAL:
        team_chat.score += 2
    elif task.task_type == TaskType.EXTREME:
        team_chat.score += 3
