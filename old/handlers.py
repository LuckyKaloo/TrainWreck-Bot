# --- Basic handlers ---
import random
from enum import StrEnum, auto
from typing import override

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CommandHandler, ConversationHandler, CallbackQueryHandler

from checks import guard, chat_not_assigned_check, valid_game_id_check, is_admin_chat_check, \
    team_chat_is_assigned_check, \
    location_chat_is_assigned_check, no_callback_check, is_runner_check, chats_all_assigned_check, \
    game_not_started_check, game_not_paused_check, game_is_started_check, game_is_paused_check
from common import games, Team, Game, Chat, chat_id_to_chat, chat_id_to_team, Task, Powerup, chat_id_to_game, \
    all_powerups


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="Welcome to TrainWreck! Type /help for a list of commands.",
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

    if update.effective_chat.id == games[0].admin_chat.chat_id:
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

    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text)


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = chat_id_to_chat(update.effective_chat.id)
    if chat.callback_message is None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="No operation to cancel")
        return

    await chat.callback_message.edit_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Operation cancelled")


# --- Setting chats ---
@guard(chat_not_assigned_check, no_callback_check)
async def create_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    while True:
        game_id = random.randint(100000, 999999)
        if game_id not in games:
            break

    games[game_id] = Game(game_id=game_id, admin_chat=Chat(update.effective_chat.id))
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"New game created with game id: {game_id}, this chat is the admin chat of the game\n\n"
            "Use this id to set the team and location chats via /create_team_<team number> and /create_location_chat"
        ),
    )


async def _create_team_helper(update: Update, context: ContextTypes.DEFAULT_TYPE, team_index: int):
    game_id = int(context.args[0])
    game = games[game_id]

    if game.teams[team_index] is not None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"Team {team_index + 1} already exists for this game\n\n"
                "Please choose a different team number or ask your admin to delete the chat for this team"
            ),
        )
        return

    game.teams[team_index] = Team(chat=Chat(update.effective_chat.id))
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=f"This chat has been assigned to Team {team_index + 1}.",
    )

@guard(valid_game_id_check, chat_not_assigned_check, no_callback_check)
async def create_team_1_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _create_team_helper(update, context, 0)

@guard(valid_game_id_check, chat_not_assigned_check, no_callback_check)
async def create_team_2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _create_team_helper(update, context, 1)

@guard(valid_game_id_check, chat_not_assigned_check, no_callback_check)
async def create_team_3_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _create_team_helper(update, context, 2)


@guard(valid_game_id_check, chat_not_assigned_check, no_callback_check)
async def create_location_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game_id = int(context.args[0])
    games[game_id].location_chat = Chat(update.effective_chat.id)
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="This chat has been assigned as the location chat",
    )


# --- Deleting chats (admin only) ---
@guard(is_admin_chat_check, game_not_started_check, no_callback_check)
async def delete_all_chats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = chat_id_to_game(update.effective_chat.id)
    del games[game.game_id]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="The game and all associated chat assignments have been deleted",
    )


async def _delete_team_helper(update: Update, context: ContextTypes.DEFAULT_TYPE, team_index: int):
    game = chat_id_to_game(update.effective_chat.id)
    game.teams[team_index] = None
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Team {team_index + 1} chat assignment has been deleted",
    )


@guard(is_admin_chat_check, game_not_started_check, no_callback_check, team_chat_is_assigned_check(0))
async def delete_team_1_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _delete_team_helper(update, context, 0)


@guard(is_admin_chat_check, game_not_started_check, no_callback_check, team_chat_is_assigned_check(1))
async def delete_team_2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _delete_team_helper(update, context, 1)


@guard(is_admin_chat_check, game_not_started_check, no_callback_check, team_chat_is_assigned_check(2))
async def delete_team_3_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _delete_team_helper(update, context, 2)


@guard(is_admin_chat_check, game_not_started_check, location_chat_is_assigned_check, no_callback_check)
async def delete_location_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = chat_id_to_game(update.effective_chat.id)
    game.location_chat_id = None
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="The location chat assignment has been deleted",
    )


# --- Drawing cards helper functions ---
def _draw_tasks(team: Team, num_tasks: int, *, extremes_only=False) -> list[Task]:
    random.shuffle(team.undrawn_tasks)
    if not extremes_only:
        new_tasks = team.undrawn_tasks[:num_tasks]
        team.shown_tasks += new_tasks
        team.undrawn_tasks = team.undrawn_tasks[num_tasks:]
    else:
        count = 0
        new_tasks = []
        while count < 3:
            task = team.undrawn_tasks.pop(0)
            if task.type == "extreme":
                team.shown_tasks.append(task)
                new_tasks.append(task)
                count += 1
            else:
                team.undrawn_tasks.append(task)

    return new_tasks

def _draw_powerups(team: Team, num_powerups: int) -> list[Powerup]:
    random.shuffle(team.undrawn_powerups)
    new_powerups = team.undrawn_powerups[:num_powerups]
    team.shown_powerups += new_powerups
    team.undrawn_powerups = team.undrawn_powerups[num_powerups:]
    return new_powerups

def _select_task(team: Team, task_index: int, *, delete_shown_tasks=True) -> Task:
    task = team.shown_tasks.pop(task_index)
    team.drawn_tasks.append(task)

    if delete_shown_tasks:
        team.undrawn_tasks += team.shown_tasks
        team.shown_tasks = []

    return task

def _select_powerup(team: Team, powerup_index: int) -> Powerup:
    powerup = team.shown_powerups.pop(powerup_index)
    team.drawn_powerups.append(powerup)
    team.undrawn_powerups += team.shown_powerups
    team.shown_powerups = []
    return powerup

async def _send_task_select_keyboard(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    team = chat_id_to_team(chat_id)
    keyboard = [[InlineKeyboardButton(
        text=f"Task {task_index + 1}", callback_data=CompleteTaskCallbacks.SELECT_TASK + f":{task_index}",
    )] for task_index in range(len(team.shown_tasks))]
    team.chat.callback_message = await context.bot.send_message(
        chat_id=chat_id, text="Select your task:", reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def _send_powerup_select_keyboard(chat_id, context: ContextTypes.DEFAULT_TYPE):
    team = chat_id_to_team(chat_id)
    keyboard = [[InlineKeyboardButton(
        text=f"Powerup {powerup_index + 1}", callback_data=CompleteTaskCallbacks.SELECT_TASK + f":{powerup_index}",
    )] for powerup_index in range(len(team.shown_tasks))]
    team.chat.callback_message = await context.bot.send_message(
        chat_id=chat_id, text="Select your powerup:", reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def _select_task_callback(update: Update):
    query = update.callback_query
    await query.answer()
    await update.effective_message.delete()

    team = chat_id_to_team(update.effective_chat.id)

    task_index = int(query.data.split(":")[-1])
    _select_task(team, task_index)

async def _select_powerup_callback(update: Update):
    query = update.callback_query
    await query.answer()
    await update.effective_message.delete()

    team = chat_id_to_team(update.effective_chat.id)

    powerup_index = int(query.data.split(":")[-1])
    _select_powerup(team, powerup_index)


# --- Starting and ending games ---
async def _start_cycle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = chat_id_to_game(update.effective_chat.id)
    running_team = game.game_state.running_team

    for team in game.teams:
        if team != running_team:
            text = "The game has started! You are the chasers, please wait 20 minutes before starting your chase"
        else:
            text = "The game has started! You are the runners, please send your location into the location chat"
        await context.bot.send_message(chat_id=team.chat.chat_id, text=text)

    for task in _draw_tasks(running_team, 3):
        await context.bot.send_photo(chat_id=running_team.chat.chat_id, photo=task.image)
    await _send_task_select_keyboard(running_team.chat.chat_id, context)

@guard(is_admin_chat_check, game_not_started_check, chats_all_assigned_check, no_callback_check)
async def start_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = chat_id_to_game(update.effective_chat.id)

    game.game_state.is_started = True
    game.game_state.running_team = game.teams[0]

    await _start_cycle(update, context)

@guard(is_admin_chat_check, game_is_started_check, no_callback_check)
async def end_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = chat_id_to_game(update.effective_chat.id)

    game.game_state.is_started = False


@guard(is_admin_chat_check, game_is_started_check, game_not_paused_check, no_callback_check)
async def catch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = chat_id_to_game(update.effective_chat.id)

    game.game_state.is_paused = True
    game.game_state.cycle_num += 1
    game.game_state.all_or_nothing = game.game_state.buy_get_free = False

    for team_index, team in enumerate(game.teams):
        if team == game.game_state.running_team:
            game.game_state.running_team = game.teams[(team_index + 1) % 3]

            team.undrawn_tasks += team.shown_tasks + team.drawn_tasks
            team.undrawn_powerups = all_powerups.copy()
            team.shown_tasks = []
            team.drawn_tasks = []
            team.shown_powerups = []
            team.drawn_powerups = []

        if team.chat.callback_message is not None:
            await team.chat.callback_message.delete()
            team.chat.callback_message = None

        await context.bot.send_message(
            chat_id=team.chat.chat_id,
            text="The runners have been caught and the game has been paused, it will be restarted by an admin soon"
        )

@guard(is_admin_chat_check, game_is_started_check, game_is_paused_check, no_callback_check)
async def restart_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = chat_id_to_game(update.effective_chat.id)

    game.game_state.is_paused = False

    await _start_cycle(update, context)

# --- Complete task conversation handlers ---
class CompleteTaskStates(StrEnum):
    @override
    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return "complete_task:" + name.lower()

    REVEAL_ADDITIONAL = auto()
    SELECTING_3_TASKS = auto()
    SELECTING_6_TASKS = auto()
    SELECTING_3_POWERUPS = auto()

class CompleteTaskCallbacks(StrEnum):
    @override
    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return "complete_task:" + name.lower()

    REVEAL_ADDITIONAL_TASKS = auto()
    REVEAL_ADDITIONAL_POWERUPS = auto()
    SELECT_TASK = auto()
    SELECT_POWERUP = auto()


@guard(game_is_started_check, game_not_paused_check, no_callback_check, is_runner_check)
async def complete_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    team = chat_id_to_team(update.effective_chat.id)

    for task in _draw_tasks(team, 3):
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=task.image)

    keyboard = [
        [InlineKeyboardButton(text="Reveal 3 more tasks", callback_data=CompleteTaskCallbacks.REVEAL_ADDITIONAL_TASKS)],
        [InlineKeyboardButton(text="Reveal 3 more powerups", callback_data=CompleteTaskCallbacks.REVEAL_ADDITIONAL_POWERUPS)],
    ]
    team.chat.callback_message = await context.bot.send_message(
        chat_id=update.effective_chat.id, text="You may reveal 3 more tasks or 3 more powerups",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CompleteTaskStates.REVEAL_ADDITIONAL

@guard(game_is_started_check, game_not_paused_check, is_runner_check)
async def reveal_additional_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await update.effective_message.delete()

    team = chat_id_to_team(update.effective_chat.id)
    for task in _draw_tasks(team, 3):
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=task.image)
    await _send_task_select_keyboard(update.effective_chat.id, context)

    return CompleteTaskStates.SELECTING_6_TASKS

@guard(game_is_started_check, game_not_paused_check, is_runner_check)
async def reveal_additional_powerups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await update.effective_message.delete()

    team = chat_id_to_team(update.effective_chat.id)

    for powerup in _draw_powerups(team, 3):
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=powerup.image)
    await _send_task_select_keyboard(update.effective_chat.id, context)

    return CompleteTaskStates.SELECTING_3_TASKS

@guard(game_is_started_check, game_not_paused_check, is_runner_check)
async def select_3_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await _select_task_callback(update)

    team = chat_id_to_team(update.effective_chat.id)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="You have chosen this task:")
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=team.drawn_tasks[0].image)

    await _send_powerup_select_keyboard(update, context)

    return CompleteTaskStates.SELECTING_3_POWERUPS

@guard(game_is_started_check, game_not_paused_check, is_runner_check)
async def select_3_powerups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _select_powerup_callback(update)

    team = chat_id_to_team(update.effective_chat.id)
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="You currently have the following powerups:"
    )
    for powerup in team.drawn_powerups:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=powerup.image)

    return ConversationHandler.END

@guard(game_is_started_check, game_not_paused_check, is_runner_check)
async def select_6_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _select_task_callback(update)

    team = chat_id_to_team(update.effective_chat.id)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="You have chosen this task:")
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=team.drawn_tasks[0].image)

    return ConversationHandler.END

# --- Assigning handlers ---
def set_handlers(application: Application):
    handlers = [
        CommandHandler("start", start_handler),
        CommandHandler("help", help_handler),
        CommandHandler("cancel", cancel_handler),
        CommandHandler("create_game", create_game_handler),
        CommandHandler("create_team_1", create_team_1_handler, has_args=True),
        CommandHandler("create_team_2", create_team_2_handler, has_args=True),
        CommandHandler("create_team_3", create_team_3_handler, has_args=True),
        CommandHandler("create_location_chat", create_location_chat_handler, has_args=True),

        ConversationHandler(
            entry_points=[CommandHandler("complete_task", complete_task_handler)],
            states={
                CompleteTaskStates.REVEAL_ADDITIONAL: [
                    CallbackQueryHandler(
                        reveal_additional_tasks_handler, CompleteTaskCallbacks.REVEAL_ADDITIONAL_TASKS
                    ),
                    CallbackQueryHandler(
                        reveal_additional_powerups_handler, CompleteTaskCallbacks.REVEAL_ADDITIONAL_POWERUPS
                    )
                ],
                CompleteTaskStates.SELECTING_3_TASKS: [CallbackQueryHandler(
                    select_3_tasks_handler, CompleteTaskCallbacks.SELECT_TASK
                )],
                CompleteTaskStates.SELECTING_3_POWERUPS: [CallbackQueryHandler(
                    select_3_powerups_handler, CompleteTaskCallbacks.SELECT_POWERUP
                )],
                CompleteTaskStates.SELECTING_6_TASKS: [CallbackQueryHandler(
                    select_6_tasks_handler, CompleteTaskCallbacks.SELECT_TASK
                )]
            },
            fallbacks=[CommandHandler("cancel", cancel_handler)]
        )
    ]

    application.add_handlers(handlers)