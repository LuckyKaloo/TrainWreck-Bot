from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

@dataclass
class Task:
    type: Literal["normal", "extreme"]
    image: Path

@dataclass
class Powerup:
    image: Path
    send_to_chasers: bool

@dataclass
class Rule:
    image: Path

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

for card_path in Path("cards").iterdir():
    if not card_path.is_file():
        continue

    card_info = card_path.name.split(" ")
    card_type = card_info[0].lower()
    if card_type == "normal":
        all_tasks.append(Task(type="normal", image=card_path))
    elif card_type == "extreme":
        all_tasks.append(Task(type="extreme", image=card_path))
    elif card_type == "powerup":
        card_info_1 = card_info[1].lower()
        if card_info_1 == "true":
            send_to_chasers = True
        elif card_info_1 == "false":
            send_to_chasers = False
        else:
            print(f"Powerup {card_path} has an invalid name!")
            continue

        all_powerups.append(Powerup(image=card_path, send_to_chasers=send_to_chasers))
    elif card_type == "rule":
        all_rules.append(Rule(image=card_path))

game = Game()

