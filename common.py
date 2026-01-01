from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Final, final

from telegram import Message


# --- Data classes ---
@final
@dataclass
class Task:
    type: Literal["normal", "extreme"]
    image: Path
    id: int

@final
@dataclass
class Powerup:
    image: Path
    send_to_chasers: bool
    id: int

@final
@dataclass
class Rule:
    image: Path
    id: int

@dataclass
class Chat:
    chat_id: Final[int]
    callback_message: Message | None = None

@dataclass
class Team:
    chat: Final[Chat]
    undrawn_tasks: list[Task] = field(default_factory=lambda: all_tasks.copy())
    shown_tasks: list[Task] = field(default_factory=list)
    drawn_tasks: list[Task] = field(default_factory=list)
    undrawn_powerups: list[Powerup] = field(default_factory=lambda: all_powerups.copy())
    shown_powerups: list[Powerup] = field(default_factory=list)
    drawn_powerups: list[Powerup] = field(default_factory=list)

@dataclass
class GameState:
    is_started: bool = False
    is_paused: bool = False
    cycle_num: int = 1
    all_or_nothing: bool = False
    buy_get_free: bool = False
    running_team: Team = None

@dataclass
class Game:
    game_id: Final[int]
    admin_chat: Final[Chat]
    location_chat: Chat | None = None
    teams: list[Team | None] = field(default_factory=lambda: [None, None, None])
    game_state: Final[GameState] = field(default_factory=lambda: GameState())


# --- Loading cards ---
_POWERUPS_SEND_TO_CHASERS = [1, 2, 3, 4, 5, 8, 9]

all_tasks = []
all_powerups = []
all_rules = []

for card_path in Path("cards").iterdir():
    if not card_path.is_file():
        continue

    card_info = card_path.stem.split(" ")
    if card_info[0] == "Location":
        if card_info[1] == "N":
            all_tasks.append(Task(type="normal", image=card_path, id=int(card_info[2])))
        elif card_info[1] == "E":
            all_tasks.append(Task(type="extreme", image=card_path, id=int(card_info[2])))
    elif card_info[0] == "Powerup":
        send_to_chasers = int(card_info[1]) in _POWERUPS_SEND_TO_CHASERS
        all_powerups.append(Powerup(image=card_path, send_to_chasers=send_to_chasers, id=int(card_info[1])))
    elif card_info[0] == "Rule":
        all_rules.append(Rule(image=card_path, id=int(card_info[1])))

games: dict[int, Game] = {}  # Maps game IDs to Game instances


# --- Helper functions ---
def chat_id_to_team(chat_id: int) -> Team | None:
    for game in games.values():
        for team in game.teams:
            if team is not None and team.chat.chat_id == chat_id:
                return team

    return None

def chat_id_to_game(chat_id: int) -> Game | None:
    for game in games.values():
        if game.admin_chat.chat_id == chat_id or game.location_chat.chat_id == chat_id:
            return game
        for team in game.teams:
            if team is not None and team.chat.chat_id == chat_id:
                return game

    return None

def chat_id_to_chat(chat_id: int) -> Chat | None:
    for game in games.values():
        if game.admin_chat.chat_id == chat_id:
            return game.admin_chat
        elif game.location_chat is not None and game.location_chat.chat_id == chat_id:
            return game.location_chat
        else:
            for team in game.teams:
                if team is not None and team.chat.chat_id == chat_id:
                    return team.chat

    return None

def is_team_chat(chat_id: int) -> bool:
    return chat_id_to_team(chat_id) is not None

def is_admin_chat(chat_id: int) -> bool:
    return admin_chat_id_to_game(chat_id) is not None

def is_location_chat(chat_id: int) -> bool:
    return any([game.location_chat is not None and chat_id == game.location_chat.chat_id for game in games.values()])
