import random
from enum import Enum, auto
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, Update, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, CommandHandler

from db import engine
from mappings import ChatRole, Game, GameChat, Card, CardType, PowerupSpecial, TaskSpecial, TeamCardJoin, CardState, \
    B1G1FStates, \
    PowerupCard, TaskCard
from utils import CheckFailedError, add_points, card_callback_generator, card_callback_pattern, \
    create_shown_task_selector, \
    get_game_chat_or_raise, \
    get_chat_id, get_tasks, validate_callback_query, validate_game_id, \
    ensure_running_team_chat, \
    graceful_fail, generate_shown_tasks, \
    to_started_game, ensure_admin_chat, db_select_card, generate_shown_powerups, \
    create_shown_powerup_selector, get_powerups, no_callback


# --- General handlers ---
async def start_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    _ = await context.bot.send_message(
        get_chat_id(tele_update), "Welcome to TrainWreck! Type /help for a list of commands.",
    )


async def rules_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        rule_cards = session.scalars(
            select(Card).where(Card.card_type == CardType.RULE),
        ).all()

        for rule_card in rule_cards:
            _ = await context.bot.send_photo(
                get_chat_id(tele_update), rule_card.image_path,
            )


# TODO
async def help_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            chat = get_game_chat_or_raise(session, tele_update)
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

        _ = await context.bot.send_message(chat_id=get_chat_id(tele_update), text=help_text)


@graceful_fail
async def cancel_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = get_game_chat_or_raise(session, tele_update)
        chat_id = chat.chat_id

        if chat.callback_message_id is None:
            _ = await context.bot.send_message(
                chat_id, "No operation to cancel",
            )
            return

        _ = await context.bot.edit_message_reply_markup(
            chat_id, chat.callback_message_id, reply_markup=None,
        )
        _ = await context.bot.send_message(
            chat_id, "Operation cancelled",
        )
        chat.callback_message_id = None

        session.commit()


# --- Creating teams ---
@graceful_fail
@no_callback
async def create_game_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        while True:
            game_id = random.randint(100000, 999999)
            if session.get(Game, game_id) is None:
                break

        chat_id = get_chat_id(tele_update)

        session.add(Game(game_id=game_id))
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
    @graceful_fail
    @no_callback
    async def create_team_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
        with Session(engine) as session:
            game = validate_game_id(session, context)
            if getattr(game, f"team_{team_num}_chat") is not None:
                raise CheckFailedError(
                    f"Team chat already exists, choose another team number or ask your admin to delete team {team_num}'s chat",
                )

            chat_id = get_chat_id(tele_update)
            team_chat = GameChat(chat_id=chat_id, game_id=game.game_id, role=ChatRole(f"team_{team_num}"))
            session.add(team_chat)

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


@graceful_fail
@no_callback
async def create_location_chat_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        game = validate_game_id(session, context)
        if game.location_chat is not None:
            raise CheckFailedError(
                f"Location chat already exists, choose another team number or ask your admin to delete the location chat",
            )

        chat_id = get_chat_id(tele_update)
        location_chat = GameChat(chat_id=chat_id, game_id=game.game_id, role=ChatRole.LOCATION)
        session.add(location_chat)
        session.commit()

        _ = await context.bot.send_message(
            chat_id,
            f"This chat has been assigned as the location chat",
        )


# --- Deleting chats (admin only) ---
@graceful_fail
@no_callback
async def delete_game_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = ensure_admin_chat(session, tele_update)
        game = chat.game
        session.delete(game)
        session.commit()

        _ = await context.bot.send_message(
            get_chat_id(tele_update),
            "Game successfully deleted, all chats have been unassigned",
        )


def delete_team_handler_generator(team_num: Literal[1, 2, 3]):
    @graceful_fail
    @no_callback
    async def delete_team_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
        with Session(engine) as session:
            chat = ensure_admin_chat(session, tele_update)
            game = chat.game
            team_chat: GameChat | None = cast(GameChat | None, getattr(game, f"team_{team_num}_chat"))
            if team_chat is None:
                raise CheckFailedError(f"Team {team_num} chat does not exist, cannot delete")

            session.delete(team_chat)
            session.commit()

            _ = await context.bot.send_message(
                get_chat_id(tele_update),
                f"Team {team_num} chat successfully deleted, team can now create a new chat assignment",
            )

            session.commit()

    return delete_team_handler


@graceful_fail
@no_callback
async def delete_location_chat_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = ensure_admin_chat(session, tele_update)
        game = chat.game
        location_chat: GameChat | None = game.location_chat
        if location_chat is None:
            raise CheckFailedError(f"Location chat does not exist, cannot delete")

        session.delete(location_chat)
        session.commit()

        _ = await context.bot.send_message(
            get_chat_id(tele_update),
            f"Location chat successfully deleted, a new location chat can now be created",
        )


# --- Starting and ending games ---
class StartCycleStates(Enum):
    DRAWING_TASKS = auto()


class StartCycleActions(Enum):
    SELECT_TASK = auto()


async def _start_cycle(session: Session, tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = ensure_admin_chat(session, tele_update)
    game = to_started_game(chat.game)
    running_chat_id = game.running_team_chat.chat_id
    for team_num in range(1, 4):
        team_chat: GameChat = cast(GameChat, getattr(game, f"team_{team_num}_chat"))
        if team_chat.chat_id == running_chat_id:
            text = "The game has started! You are the runners, please send your location into the location chat"
        else:
            text = "The game has started! You are the chasers, please wait 20 minutes before starting your chase"
        _ = await context.bot.send_message(team_chat.chat_id, text)

    for task in generate_shown_tasks(session, running_chat_id, 3, False):
        _ = await context.bot.send_photo(running_chat_id, task.image_path)

    keyboard_markup = create_shown_task_selector(
        session, running_chat_id, StartCycleActions.SELECT_TASK
    )
    callback_message = await context.bot.send_message(
        running_chat_id, "Select your task:", reply_markup=keyboard_markup,
    )
    game.running_team_chat.callback_message_id = callback_message.message_id

    session.commit()


@graceful_fail
@no_callback
async def start_game_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = ensure_admin_chat(session, tele_update)
        game = chat.game
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

        assert game.team_1_chat is not None, "team_1_chat should not be None here"
        game.running_team_chat_id = game.team_1_chat.chat_id

        game.is_started = True

        await _start_cycle(session, tele_update, context)

        session.commit()


@graceful_fail
@no_callback
async def end_game_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = ensure_admin_chat(session, tele_update)
        game = chat.game
        if not game.is_started:
            raise CheckFailedError("Game is not started")

        game.is_started = False

        _ = await context.bot.send_message(
            get_chat_id(tele_update),
            "Game successfully ended, teams can now wait for the next game or ask their admin to restart the game",
        )

        session.commit()


@graceful_fail
@no_callback
async def catch_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = ensure_admin_chat(session, tele_update)
        game = chat.game
        started_game = to_started_game(game)
        if started_game.is_paused:
            raise CheckFailedError("Game is currently paused, cannot register catch")

        running_team_chat = started_game.running_team_chat
        if running_team_chat.callback_message_id is not None:
            _ = await context.bot.edit_message_reply_markup(
                get_chat_id(tele_update), running_team_chat.callback_message_id, reply_markup=None,
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
        game.all_or_nothing = False
        game.B1G1F = B1G1FStates.INACTIVE

        _ = await context.bot.send_message(
            get_chat_id(tele_update),
            "Catch registered, the next team is now the running team. Use /restart_game to start the next cycle.",
        )

        session.commit()


@graceful_fail
@no_callback
async def restart_game_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = ensure_admin_chat(session, tele_update)
        game = chat.game
        if not game.is_paused:
            raise CheckFailedError("Game is not paused, cannot restart game")

        game.is_paused = False

        await _start_cycle(session, tele_update, context)

        session.commit()


# --- Complete task handlers ---
class CompleteTaskActions(Enum):
    REVEAL_TASKS_OR_POWERUPS = auto()
    SELECT_TASK = auto()
    SELECT_POWERUP = auto()
    FULLERTON = auto()
    B1G1F = auto()
    DREW_B1G1F = auto()


async def _send_select_task_message(session: Session, chat: GameChat, context: ContextTypes.DEFAULT_TYPE):
    B1G1F = chat.game.B1G1F
    chat_id = chat.chat_id
    keyboard = create_shown_task_selector(session, chat_id, CompleteTaskActions.SELECT_TASK)

    if B1G1F == B1G1FStates.NONE_DRAWN:
        text = "Select your first task to draw:"
    elif B1G1F == B1G1FStates.ONE_DRAWN:
        text = "Select your second task to draw:"
    elif B1G1F != B1G1FStates.INACTIVE:
        raise RuntimeError(f"Invalid B1G1F state when drawing tasks: {B1G1F}")
    else:
        text = "Select a task to draw:"

    callback_message = await context.bot.send_message(chat_id, text, reply_markup=keyboard)
    chat.callback_message_id = callback_message.message_id

    session.commit()


async def _send_select_powerup_message(session: Session, chat: GameChat, context: ContextTypes.DEFAULT_TYPE,
                                       enum_value: Enum):
    chat_id = chat.chat_id
    keyboard = create_shown_powerup_selector(session, chat_id, enum_value)

    callback_message = await context.bot.send_message(
        chat_id, "Select a powerup to draw:", reply_markup=keyboard,
    )
    chat.callback_message_id = callback_message.message_id


@graceful_fail
async def on_select_task(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat, data = await validate_callback_query(session, tele_update, context)
        game = chat.game
        B1G1F = game.B1G1F

        card_id = int(data.split(":")[-1])
        selected_task = db_select_card(session, chat, card_id, not B1G1F == B1G1FStates.NONE_DRAWN)

        _ = await context.bot.send_message(get_chat_id(tele_update), "You have selected the following task:")
        _ = await context.bot.send_photo(get_chat_id(tele_update), selected_task.image_path)

        if B1G1F == B1G1FStates.NONE_DRAWN:
            game.B1G1F = B1G1FStates.ONE_DRAWN
            session.commit()
            await _send_select_task_message(session, chat, context)
        elif B1G1F == B1G1FStates.ONE_DRAWN:
            game.B1G1F = B1G1FStates.BOTH_DRAWN
        elif B1G1F != B1G1FStates.INACTIVE:
            raise RuntimeError(f"Invalid B1G1F state when drawing tasks: {B1G1F}")

        game.all_or_nothing = False

        session.commit()


@graceful_fail
async def on_select_powerup(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat, data = await validate_callback_query(session, tele_update, context)

        card_id = int(data.split(":")[-1])
        selected_powerup = db_select_card(session, chat, card_id, False)
        if not isinstance(selected_powerup, PowerupCard):
            raise RuntimeError("Selected card is not a powerup card")
        _ = await context.bot.send_message(get_chat_id(tele_update), "You have selected the following powerup:")
        _ = await context.bot.send_photo(get_chat_id(tele_update), selected_powerup.image_path)

        shown_tasks = get_tasks(session, chat.chat_id, CardState.SHOWN)

        if selected_powerup.powerup_special == PowerupSpecial.BUY_1_GET_1_FREE and len(shown_tasks) >= 2:
            keyboard = InlineKeyboardMarkup.from_column(
                [
                    InlineKeyboardButton(
                        "Use powerup immediately",
                        callback_data=f"{card_callback_generator(CompleteTaskActions.DREW_B1G1F)}:USE",
                    ),
                    InlineKeyboardButton(
                        "Save powerup for later",
                        callback_data=f"{card_callback_generator(CompleteTaskActions.DREW_B1G1F)}:KEEP",
                    ),
                ],
            )
            callback_message = await context.bot.send_message(
                chat.chat_id,
                "Do you want to use the Buy 1 Get 1 Free powerup now or save it for later?",
                reply_markup=keyboard,
            )
            chat.callback_message_id = callback_message.message_id
        else:
            _ = await _send_select_task_message(session, chat, context)

        session.commit()


@graceful_fail
async def on_B1G1F_use_or_keep(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat, data = await validate_callback_query(session, tele_update, context)
        game = chat.game

        choice = data.split(":")[-1]
        if choice == "USE":
            game.B1G1F = B1G1FStates.NONE_DRAWN

            team_card_join = session.scalars(
                select(TeamCardJoin)
                .join(PowerupCard, TeamCardJoin.card_id == PowerupCard.card_id)
                .where(
                    TeamCardJoin.team_chat_id == chat.chat_id,
                    TeamCardJoin.state == CardState.DRAWN,
                    PowerupCard.powerup_special == PowerupSpecial.BUY_1_GET_1_FREE,
                ),
            ).one_or_none()
            if team_card_join is None:
                raise RuntimeError("No Buy 1 Get 1 Free powerup card found to use")
            team_card_join.state = CardState.USED

        await _send_select_task_message(session, chat, context)
        session.commit()


async def _draw_new_cards(
    session: Session, chat: GameChat, context: ContextTypes.DEFAULT_TYPE,
    num_cards: int, extremes_only: bool, reveal_more: bool
):
    chat_id = chat.chat_id
    for task in generate_shown_tasks(session, chat_id, num_cards, extremes_only):
        _ = await context.bot.send_photo(chat_id, task.image_path)

    if not reveal_more:
        await _send_select_task_message(session, chat, context)
        return

    keyboard = InlineKeyboardMarkup.from_column(
        [
            InlineKeyboardButton(
                "Reveal 3 more tasks",
                callback_data=f"{card_callback_generator(CompleteTaskActions.REVEAL_TASKS_OR_POWERUPS)}:TASKS",
            ),
            InlineKeyboardButton(
                "Reveal 3 powerups",
                callback_data=f"{card_callback_generator(CompleteTaskActions.REVEAL_TASKS_OR_POWERUPS)}:POWERUPS",
            ),
        ],
    )
    callback_message = await context.bot.send_message(
        chat_id, "Choose whether to reveal 3 more tasks or 3 more powerups", reply_markup=keyboard,
    )
    chat.callback_message_id = callback_message.message_id

    session.commit()


async def on_reveal(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat, data = await validate_callback_query(session, tele_update, context)
        chat_id = chat.chat_id
        game = chat.game

        choice = data.split(":")[-1]

        if choice == "TASKS":
            for task in generate_shown_tasks(session, chat_id, 3, game.all_or_nothing):
                _ = await context.bot.send_photo(chat_id, task.image_path)

            await _send_select_task_message(session, chat, context)
        elif choice == "POWERUPS":
            for powerup in generate_shown_powerups(session, chat_id, 3):
                _ = await context.bot.send_photo(chat_id, powerup.image_path)

            await _send_select_powerup_message(session, chat, context, CompleteTaskActions.SELECT_POWERUP)
        else:
            raise RuntimeError(f"Invalid choice for reveal: {choice}")

        session.commit()


async def _get_task_info(session: Session, card: TaskCard, chat: GameChat, context: ContextTypes.DEFAULT_TYPE):
    if card.task_special == TaskSpecial.FULLERTON:
        keyboard = InlineKeyboardMarkup.from_column(
            [
                InlineKeyboardButton(
                    "Arrived early/on time",
                    callback_data=f"{card_callback_generator(CompleteTaskActions.FULLERTON)}:EARLY",
                ),
                InlineKeyboardButton(
                    "Arrived late", callback_data=f"{card_callback_generator(CompleteTaskActions.FULLERTON)}:LATE",
                ),
            ],
        )
        callback_message = await context.bot.send_message(
            chat.chat_id,
            "Did you arrive at your chosen location early/on time or late?",
            reply_markup=keyboard,
        )
        chat.callback_message_id = callback_message.message_id
    else:
        if card.task_special == TaskSpecial.NONE:
            num_cards = 3
        elif card.task_special == TaskSpecial.MBS:
            num_cards = random.randint(1, 3)
            _ = await context.bot.send_message(
                chat.chat_id,
                f"The dice has ordained that your next draw will reveal {num_cards} tasks",
            )
        else:
            raise RuntimeError(f"Unknown task special: {card.task_special}")

        await _draw_new_cards(session, chat, context, num_cards, chat.game.all_or_nothing, True)


@graceful_fail
async def on_fullerton_response(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat, data = await validate_callback_query(session, tele_update, context)
        game = chat.game

        response = data.split(":")[-1]
        if response == "EARLY":
            _ = await context.bot.send_message(
                chat.chat_id, "Since you arrived early/on time, the draw will proceed normally"
            )
            reveal_more = True
        elif response == "LATE":
            _ = await context.bot.send_message(
                chat.chat_id, "Since you arrived late, you will not get to reveal more cards"
            )
            reveal_more = False
        else:
            raise RuntimeError(f"Invalid Fullerton response: {response}")

        await _draw_new_cards(session, chat, context, 3, game.all_or_nothing, reveal_more)

        session.commit()


@graceful_fail
@no_callback
async def complete_task_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = ensure_running_team_chat(session, tele_update)
        game = chat.game

        team_card_joins = session.scalars(
            select(TeamCardJoin)
            .join(TaskCard, TeamCardJoin.card_id == TaskCard.card_id)
            .where(
                TeamCardJoin.team_chat_id == chat.chat_id,
                TeamCardJoin.state == CardState.DRAWN,
            ),
        ).all()
        if len(team_card_joins) == 0:
            raise CheckFailedError("No drawn tasks to complete")
        drawn_tasks: list[TaskCard] = []
        for team_card_join in team_card_joins:
            if not isinstance(team_card_join.card, TaskCard):
                raise RuntimeError("Drawn card is not a task card")
            drawn_tasks.append(team_card_join.card)

        if game.B1G1F == B1G1FStates.INACTIVE:
            if len(team_card_joins) != 1:
                raise RuntimeError("Multiple drawn tasks found despite B1G1F being inactive")

            drawn_task = drawn_tasks[0]
            team_card_joins[0].state = CardState.USED
            add_points(chat, drawn_task)

            _ = await context.bot.send_message(
                chat.chat_id,
                f"Task completed! You now have {chat.score} points.",
            )

            await _get_task_info(session, drawn_task, chat, context)
        elif game.B1G1F == B1G1FStates.BOTH_DRAWN:
            if len(team_card_joins) != 2:
                raise RuntimeError("Expected 2 drawn tasks with B1G1F BOTH_DRAWN state")
            keyboard = InlineKeyboardMarkup.from_column(
                [InlineKeyboardButton(
                    task.title,
                    callback_data=f"{card_callback_generator(CompleteTaskActions.B1G1F)}:{task.card_id}",
                ) for task in drawn_tasks],
            )
            callback_message = await context.bot.send_message(
                chat.chat_id,
                "Good job! Select which task you completed:",
                reply_markup=keyboard,
            )
            chat.callback_message_id = callback_message.message_id
        elif game.B1G1F == B1G1FStates.ONE_COMPLETED:
            if len(team_card_joins) != 1:
                raise RuntimeError("Expected 2 drawn tasks with B1G1F ONE_COMPLETED state")
            drawn_task = drawn_tasks[0]

            pending_team_card_join = session.scalars(
                select(TeamCardJoin)
                .join(TaskCard, TeamCardJoin.card_id == TaskCard.card_id)
                .where(
                    TeamCardJoin.team_chat_id == chat.chat_id,
                    TeamCardJoin.state == CardState.PENDING,
                ),
            ).one_or_none()
            if pending_team_card_join is None:
                raise RuntimeError("No pending task found with B1G1F ONE_COMPLETED state")
            if not isinstance(pending_team_card_join.card, TaskCard):
                raise RuntimeError("Pending card is not a task card")
            pending_task = pending_team_card_join.card

            team_card_joins[0].state = CardState.USED
            pending_team_card_join.state = CardState.USED
            add_points(chat, drawn_task)
            add_points(chat, pending_task)

            if chat.score is None:
                raise RuntimeError("Team chat has no score")
            chat.score += 2

            _ = await context.bot.send_message(
                chat.chat_id,
                f"Both tasks completed! You now have {chat.score} points.",
            )

        session.commit()


@graceful_fail
async def on_B1G1F_select_completed_task(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat, data = await validate_callback_query(session, tele_update, context)

        card_id = int(data.split(":")[-1])
        team_card_join = session.scalars(
            select(TeamCardJoin)
            .join(TaskCard, TeamCardJoin.card_id == TaskCard.card_id)
            .where(
                TeamCardJoin.card_id == card_id,
                TeamCardJoin.team_chat_id == chat.chat_id,
                TeamCardJoin.state == CardState.DRAWN,
            ),
        ).one_or_none()
        if team_card_join is None:
            raise CheckFailedError("No drawn task found with that ID")
        selected_task = team_card_join.card
        if not isinstance(selected_task, TaskCard):
            raise RuntimeError("Selected card is not a task card")
        team_card_join.state = CardState.PENDING

        # TODO: cannot use _get_task_info cos it calls _draw_new_cards, need to add num_tasks and reveal_next to game
        await _get_task_info(session, selected_task, chat, context)

        session.commit()


# --- Mid-cycle handlers ---
@graceful_fail
@no_callback
async def current_task_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = ensure_running_team_chat(session, tele_update)
        chat_id = chat.chat_id
        drawn_tasks = get_tasks(session, chat_id, CardState.DRAWN)
        if len(drawn_tasks) == 0:
            raise CheckFailedError("No drawn tasks found")
        for task in drawn_tasks:
            _ = await context.bot.send_photo(chat_id, task.image_path)

        session.commit()


@graceful_fail
@no_callback
async def show_powerups_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = ensure_running_team_chat(session, tele_update)
        chat_id = chat.chat_id
        drawn_powerups = get_powerups(session, chat_id, CardState.DRAWN)
        if len(drawn_powerups) == 0:
            raise CheckFailedError("No drawn tasks found")
        for powerup in drawn_powerups:
            _ = await context.bot.send_photo(chat_id, powerup.image_path)

        session.commit()


class UsePowerupStates(Enum):
    SELECTING_POWERUP = auto()


@graceful_fail
@no_callback
async def use_powerup_handler(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat = ensure_running_team_chat(session, tele_update)
        chat_id = chat.chat_id

        drawn_powerups = get_powerups(session, chat_id, CardState.DRAWN)
        if len(drawn_powerups) == 0:
            raise CheckFailedError("No shown powerups found")
        for powerup in drawn_powerups:
            _ = await context.bot.send_photo(chat_id, powerup.image_path)
        keyboard = create_shown_powerup_selector(session, chat_id, CardState.DRAWN)

        callback_message = await context.bot.send_message(
            chat_id, "Select a powerup to draw:", reply_markup=keyboard,
        )
        chat.callback_message_id = callback_message.message_id
        session.commit()


@graceful_fail
async def on_use_powerup_select(tele_update: Update, context: ContextTypes.DEFAULT_TYPE):
    with Session(engine) as session:
        chat, data = await validate_callback_query(session, tele_update, context)
        chat_id = chat.chat_id
        game = to_started_game(chat.game)

        card_id = int(data.split(":")[-1])
        team_card_join = session.scalars(
            select(TeamCardJoin)
            .join(PowerupCard, TeamCardJoin.card_id == PowerupCard.card_id)
            .where(
                TeamCardJoin.team_chat_id == chat.chat_id,
                TeamCardJoin.card_id == card_id,
                TeamCardJoin.state == CardState.SHOWN,
            ),
        ).one_or_none()

        if team_card_join is None:
            raise CheckFailedError("No shown powerup found with that ID")
        selected_powerup = team_card_join.card
        if not isinstance(selected_powerup, PowerupCard):
            raise RuntimeError("Selected card is not a powerup card")

        for game_chat in [game.team_1_chat, game.team_2_chat, game.team_3_chat]:
            if game_chat.chat_id != chat_id:
                _ = await context.bot.send_message(
                    game_chat.chat_id, "The runners have used the following powerup:",
                )
                _ = await context.bot.send_photo(game_chat.chat_id, selected_powerup.image_path)
            else:
                _ = await context.bot.send_message(chat_id, "You have used the following powerup:")
                _ = await context.bot.send_photo(chat_id, selected_powerup.image_path)
        team_card_join.state = CardState.USED

        if selected_powerup.powerup_special == PowerupSpecial.BUY_1_GET_1_FREE:
            game.B1G1F = B1G1FStates.NONE_DRAWN
        elif selected_powerup.powerup_special == PowerupSpecial.ALL_OR_NOTHING:
            game.all_or_nothing = True

        session.commit()


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
        CallbackQueryHandler(on_select_task, card_callback_pattern(StartCycleActions.SELECT_TASK)),

        CommandHandler("complete_task", complete_task_handler),
        CallbackQueryHandler(on_B1G1F_select_completed_task, card_callback_pattern(CompleteTaskActions.B1G1F)),
        CallbackQueryHandler(on_fullerton_response, card_callback_pattern(CompleteTaskActions.FULLERTON)),

        CallbackQueryHandler(on_reveal, card_callback_pattern(CompleteTaskActions.REVEAL_TASKS_OR_POWERUPS)),
        CallbackQueryHandler(on_select_task, card_callback_pattern(CompleteTaskActions.SELECT_TASK)),
        CallbackQueryHandler(on_select_powerup, card_callback_pattern(CompleteTaskActions.SELECT_POWERUP)),
        CallbackQueryHandler(on_B1G1F_use_or_keep, card_callback_pattern(CompleteTaskActions.DREW_B1G1F)),

        CommandHandler("current_task", current_task_handler),
        CommandHandler("show_powerups", show_powerups_handler),
        CommandHandler("use_powerup", use_powerup_handler),
        CallbackQueryHandler(on_use_powerup_select, card_callback_pattern(UsePowerupStates.SELECTING_POWERUP))
    ]

    application.add_handlers(handlers)
