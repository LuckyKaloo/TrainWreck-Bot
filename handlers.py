import os
import random

from game import game, Team, all_rules, all_powerups

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CommandHandler, CallbackQueryHandler


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("start_handler called")

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Welcome to TrainWreck! Type /help for a list of commands.")

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("help_handler called")

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

    if update.effective_chat.id == game.admin_chat_id:
        help_text += (
            "\nAdmin commands:\n"
            "/delete_team <team_number> - Deletes the specified team chat assignment\n"
            "/delete_admin_chat - Deletes the admin chat assignment"
            "/delete_location_chat - Deletes the location chat assignment\n"
            "/catch - Marks a catch as having occurred in the game, updates teams' roles amd starts timer\n"
            "/start_game - Starts the game for all teams\n"
            "/restart_game - Restarts the game for all teams\n"
        )

    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text)

async def create_team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("create_team_handler called")

    if len(context.args) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Team number not given!")
        return

    # noinspection PyBroadException
    try:
        if len(context.args) != 1:
            raise
        team_number = int(context.args[0]) - 1
        if team_number < 0 or team_number > 2:
            raise

        if game.teams[team_number] is not None:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Team number already taken!")
            return

        team = Team(chat_id=update.effective_chat.id)
        game.teams[team_number] = team
        game.chat_id_to_team[update.effective_chat.id] = team
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Team {team_number + 1} created!")
    except Exception as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Team number should be between 1 and 3!")
        return

async def rules_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("rules_handler called")

    for rule_card in all_rules:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=rule_card.image)

async def current_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("current_task_handler called")

    team = game.chat_id_to_team[update.effective_chat.id]
    if not team.is_running:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You are not currently running!")
        return

    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=team.current_task.image)

async def show_powerups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("show_powerups_handler called")

    team = game.chat_id_to_team[update.effective_chat.id]
    if not team.is_running:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You are not currently running!")
        return

    if len(team.drawn_powerups) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You currently have no powerups!")
        return

    # await context.bot.send_message(chat_id=update.effective_chat.id, text="These are your current powerups:")
    for powerup in team.drawn_powerups:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=powerup.image)

async def use_powerup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("use_powerup_handler called")

    team = game.chat_id_to_team[update.effective_chat.id]
    if not team.is_running:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You are not currently running!")
        return

    if len(team.drawn_powerups) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You currently have no powerups!")
        return

    # await context.bot.send_message(chat_id=update.effective_chat.id, text="These are your current powerups:")
    keyboard = []
    for powerup_num, powerup in enumerate(team.drawn_powerups):
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=powerup.image)
        keyboard.append([InlineKeyboardButton(f"Powerup {powerup_num + 1}", callback_data=f"use_powerup:{powerup_num}:{game.cycle_num}")])
    keyboard.append([InlineKeyboardButton("Cancel", callback_data=f"use_powerup:cancel:{game.cycle_num}")])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please choose which powerup to use:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def use_powerup_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("use_powerup_callback_handler called")

    await update.effective_message.edit_reply_markup(reply_markup=None)

    team = game.chat_id_to_team[update.effective_chat.id]

    if len(team.drawn_powerups) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You currently have no powerups!")
        return

    query = update.callback_query
    await query.answer()

    if int(query.data.split(":")[2]) != game.cycle_num:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="This draw is no longer valid!")
        return

    if query.data.split(":")[1] == "cancel":
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Powerup use cancelled.")
        return

    powerup_num = int(query.data.split(":")[1])
    powerup = team.drawn_powerups.pop(powerup_num)

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Powerup used!")
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=powerup.image)

    if powerup.send_to_chasers:
        for team in game.teams:
            if team is not None and team.chat_id != update.effective_chat.id:
                await context.bot.send_message(chat_id=team.chat_id, text="Runners have used a powerup!")
                await context.bot.send_photo(chat_id=team.chat_id, photo=powerup.image)

async def complete_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("complete_task_handler called")

    team = game.chat_id_to_team[update.effective_chat.id]
    if not team.is_running:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You are not currently running!")
        return

    if team.current_task.type == "normal":
        team.score += 2
    elif team.current_task.type == "extreme":
        team.score += 3

    if len(team.tasks) == 0:
        return

    for temp_team in game.teams:
        if temp_team.is_running:
            await context.bot.send_message(chat_id=temp_team.chat_id, text=f"Good job! Your current score is {temp_team.score}")
        else:
            await context.bot.send_message(chat_id=temp_team.chat_id, text=f"The runners have completed a task!")

    await _start_draw(team, context)

async def _start_draw(team: Team, context: ContextTypes.DEFAULT_TYPE):
    print("_start_draw called")

    random.shuffle(team.tasks)
    team.temp_tasks = team.tasks[:3]
    team.tasks = team.tasks[3:]

    keyboard = [
        [InlineKeyboardButton("Reveal 3 more tasks", callback_data=f"draw:tasks:{game.cycle_num}")],
        [InlineKeyboardButton("Reveal 3 powerups", callback_data=f"draw:powerups:{game.cycle_num}")]
    ]

    # await context.bot.send_message(chat_id=team.chat_id, text="You have drawn these 3 tasks:")
    for task in team.temp_tasks:
        await context.bot.send_photo(chat_id=team.chat_id, photo=task.image)
    await context.bot.send_message(
        chat_id=team.chat_id,
        text="Choose whether to reveal 3 more tasks or 3 powerups:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def _draw_tasks(team: Team, update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("_draw_tasks called")

    await update.effective_message.delete()

    new_tasks = team.tasks[:3]
    team.temp_tasks += team.tasks[:3]
    team.tasks = team.tasks[3:]

    keyboard = []
    for task_num, task in enumerate(team.temp_tasks):
        keyboard.append([InlineKeyboardButton(f"Task {task_num + 1}", callback_data=f"draw_tasks_1:{task_num}:{game.cycle_num}")])

    # await context.bot.send_message(chat_id=update.effective_chat.id, text="You have drawn these 6 tasks:")
    for task in new_tasks:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=task.image)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please choose which task to keep:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def _draw_tasks_1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.edit_reply_markup(reply_markup=None)

    print("_draw_tasks_1 called")

    team = game.chat_id_to_team[update.effective_chat.id]

    query = update.callback_query
    await query.answer()

    if int(query.data.split(":")[2]) != game.cycle_num:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="This draw is no longer valid!")
        return

    task_num = int(query.data.split(":")[1])
    team.current_task = team.temp_tasks.pop(task_num)
    team.tasks += team.temp_tasks
    team.temp_tasks = None

    await context.bot.send_message(chat_id=update.effective_chat.id, text="You have chosen your task:")
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=team.current_task.image)

async def _draw_powerups(team: Team, update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("_draw_powerups called")

    random.shuffle(team.powerups)

    team.temp_powerups = team.powerups[:3]
    team.powerups = team.powerups[3:]

    keyboard = []
    for task_num, task in enumerate(team.temp_tasks):
        keyboard.append([InlineKeyboardButton(f"Task {task_num + 1}", callback_data=f"draw_powerups_1:{task_num}:{game.cycle_num}")])

    # await context.bot.send_message(chat_id=update.effective_chat.id, text="You have drawn these 3 powerups:")
    for powerup in team.temp_powerups:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=powerup.image)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please choose which task to keep:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def _draw_powerups_1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.edit_reply_markup(reply_markup=None)

    print("_draw_powerups_1 called")

    team = game.chat_id_to_team[update.effective_chat.id]

    query = update.callback_query
    await query.answer()

    if int(query.data.split(":")[2]) != game.cycle_num:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="This draw is no longer valid!")
        return

    task_num = int(query.data.split(":")[1])
    team.current_task = team.temp_tasks.pop(task_num)
    team.tasks += team.temp_tasks
    team.temp_tasks = None

    await context.bot.send_message(chat_id=update.effective_chat.id, text="You have chosen your task:")
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=team.current_task.image)

    keyboard = []
    for powerup_num, powerup in enumerate(team.temp_powerups):
        keyboard.append([InlineKeyboardButton(f"Powerup {powerup_num + 1}", callback_data=f"draw_powerups_2:{powerup_num}:{game.cycle_num}")])

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please choose which powerup to keep:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def _draw_powerups_2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.edit_reply_markup(reply_markup=None)

    print("_draw_powerups_2 called")

    team = game.chat_id_to_team[update.effective_chat.id]

    query = update.callback_query
    await query.answer()

    if int(query.data.split(":")[2]) != game.cycle_num:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="This draw is no longer valid!")
        return

    powerup_num = int(query.data.split(":")[1])
    team.drawn_powerups.append(team.temp_powerups.pop(powerup_num))
    team.powerups += team.temp_powerups
    team.temp_powerups = None

    await context.bot.send_message(chat_id=update.effective_chat.id, text="You currently have the following powerups:")
    for powerup in team.drawn_powerups:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=powerup.image)

async def _draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.edit_reply_markup(reply_markup=None)

    print("_draw called")

    team = game.chat_id_to_team[update.effective_chat.id]

    query = update.callback_query
    await query.answer()

    if int(query.data.split(":")[2]) != game.cycle_num:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="This draw is no longer valid!")
        return

    data = query.data.split(":")[1]
    if data == "tasks":
        await _draw_tasks(team, update, context)
    elif data == "powerups":
        await _draw_powerups(team, update, context)

async def admin_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("admin_chat_handler called")

    if game.admin_chat_id is not None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Admin chat already exists! Delete the current admin chat")
        return

    if len(context.args) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Password not given!")
        return

    password = context.args[0]
    if password != os.getenv("ADMIN_PASSWORD"):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Password is incorrect!")
        return

    game.admin_chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Admin chat set.")

async def location_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("location_chat_handler called")

    if game.location_chat_id is not None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Location chat already exists! Delete the current location chat")
        return

    game.location_chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Location chat set.")

async def delete_team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("delete_team_handler called")

    if update.effective_chat.id != game.admin_chat_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Only the admin chat can delete teams!")
        return

    if len(context.args) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Team number not given!")
        return

    # noinspection PyBroadException
    try:
        if len(context.args) != 1:
            raise
        team_number = int(context.args[0]) - 1
        if team_number < 0 or team_number > 2:
            raise

        if game.teams[team_number] is None:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Team does not exist yet!")
        else:
            game.teams[team_number] = None
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Team deleted!")
    except:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Team number should be between 1 and 3!")

async def delete_admin_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("delete_admin_chat_handler called")

    if update.effective_chat.id != game.admin_chat_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Only the admin chat can delete the admin chat!")
        return

    game.admin_chat_id = None
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Admin chat deleted!")

async def delete_location_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("delete_location_chat_handler called")

    if update.effective_chat.id != game.admin_chat_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Only the admin chat can delete the location chat!")
        return

    game.location_chat_id = None
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Location chat deleted!")

async def catch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("catch_handler called")

    if update.effective_chat.id != game.admin_chat_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Only the admin chat can mark catches!")
        return

    running_team_num = None
    for team_num, team in enumerate(game.teams):
        if team.is_running:
            running_team_num = (team_num + 1) % 3
            if team.temp_tasks is not None:
                team.tasks += team.temp_tasks
                team.temp_tasks = None
    assert running_team_num is not None

    game.cycle_num += 1

    for team_num, team in enumerate(game.teams):
        if team_num == running_team_num:
            team.is_running = True
            team.powerups = all_powerups.copy()
            team.drawn_powerups = []
            team.temp_tasks = team.temp_powerups = None
            team.current_task = None
        else:
            team.is_running = False

        await context.bot.send_message(chat_id=team.chat_id, text=f"The runners have been caught! The game will continue once the admins restart it!")

    await context.bot.send_message(chat_id=game.location_chat_id, text="Please turn off all live locations now!")

async def _start_game(context: ContextTypes.DEFAULT_TYPE):
    print("_start_game called")

    for team in game.teams:
        if team.is_running:
            await context.bot.send_message(
                chat_id=team.chat_id,
                text="The game has started! You are the runners, please send your location into the location chat."
                )
            await _start_draw(team, context)
        else:
            await context.bot.send_message(
                chat_id=team.chat_id,
                text="The game has started! You are the chasers, wait 20 minutes before you can begin moving."
            )

async def start_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("start_game_handler called")

    if update.effective_chat.id != game.admin_chat_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Only the admin chat can start games!")
        return

    if game.is_started:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="The game has already started!")
        return

    if game.location_chat_id is None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Location chat must be set before starting the game!")
        return

    for team_num, team in enumerate(game.teams):
        if team is None:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="All teams must be created before starting the game!")
            return
        new_team = Team(chat_id=team.chat_id)
        game.teams[team_num] = new_team
        game.chat_id_to_team[team.chat_id] = new_team

    game.teams[0].is_running = True
    game.is_started = True
    game.cycle_num = 1

    await _start_game(context)

async def restart_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("restart_game_handler called")

    if update.effective_chat.id != game.admin_chat_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Only the admin chat can restart games!")
        return

    await _start_game(context)

def set_handlers(application: Application):
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("create_team", create_team_handler))
    application.add_handler(CommandHandler("rules", rules_handler))
    application.add_handler(CommandHandler("current_task", current_task_handler))
    application.add_handler(CommandHandler("show_powerups", show_powerups_handler))

    application.add_handler(CommandHandler("use_powerup", use_powerup_handler))
    application.add_handler(CallbackQueryHandler(use_powerup_callback_handler, pattern=r"^use_powerup:"))

    application.add_handler(CommandHandler("complete_task", complete_task_handler))
    application.add_handler(CallbackQueryHandler(_draw, pattern=r"^draw:"))
    application.add_handler(CallbackQueryHandler(_draw_tasks_1, pattern=r"^draw_tasks_1:"))
    application.add_handler(CallbackQueryHandler(_draw_powerups_1, pattern=r"^draw_powerups_1:"))
    application.add_handler(CallbackQueryHandler(_draw_powerups_2, pattern=r"^draw_powerups_2:"))

    application.add_handler(CommandHandler("admin_chat", admin_chat_handler))
    application.add_handler(CommandHandler("location_chat", location_chat_handler))

    application.add_handler(CommandHandler("delete_team", delete_team_handler))
    application.add_handler(CommandHandler("delete_admin_chat", delete_admin_chat_handler))
    application.add_handler(CommandHandler("delete_location_chat", delete_location_chat_handler))
    application.add_handler(CommandHandler("catch", catch_handler))
    application.add_handler(CommandHandler("start_game", start_game_handler))
    application.add_handler(CommandHandler("restart_game", restart_game_handler))

