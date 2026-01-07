from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

@dataclass
class Task:
    type: Literal["normal", "extreme"]
    image: Path
    id: int

@dataclass
class Powerup:
    image: Path
    send_to_chasers: bool
    id: int

@dataclass
class Rule:
    image: Path
    id: int

@dataclass
class Team:
    chat_id: int
    tasks: list[Task] = field(default_factory=lambda: all_tasks.copy())
    powerups: list[Powerup] = field(default_factory=lambda: all_powerups.copy())
    drawn_powerups: list[Powerup] = field(default_factory=list)
    current_task: Task = None
    temp_tasks: list[Task] = None
    temp_powerups: list[Powerup] = None
    score: int = 0
    is_running: bool = False

@dataclass
class Game:
    admin_chat_id: int = None
    location_chat_id: int = None
    teams: list[Team] = field(default_factory=lambda: [None, None, None])
    chat_id_to_team: dict[int, Team] = field(default_factory=dict)
    is_started: bool = False
    cycle_num: int = 1

all_tasks: list[Task] = []
all_powerups: list[Powerup] = []
all_rules: list[Rule] = []

_POWERUP_SEND_TO_CHASER_IDS = [1, 2, 3, 4, 5, 8, 9]

for card_path in Path("../cards").iterdir():
    if not card_path.is_file():
        continue

    card_info = card_path.name.split(" ")

    if card_info[0] == "Location":
        if card_info[1] == "N":
            all_tasks.append(Task(type="normal", image=card_path, id=int(card_info[2])))
        elif card_info[1] == "E":
            all_tasks.append(Task(type="extreme", image=card_path, id=int(card_info[2])))
    elif card_info[0] == "Powerup":
        powerup_id = int(card_info[1])
        all_powerups.append(Powerup(image=card_path, send_to_chasers=powerup_id in _POWERUP_SEND_TO_CHASER_IDS, id=powerup_id))
    elif card_info[0] == "Info":
        all_rules.append(Rule(image=card_path, id=int(card_info[1])))

    all_rules.sort(key=lambda x: x.card_id)

game = Game()

