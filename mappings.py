from enum import StrEnum
from typing import ClassVar, final
from sqlalchemy import Constraint, ForeignKey, UniqueConstraint, and_, CheckConstraint
from sqlalchemy.orm import Mapped, MappedAsDataclass, DeclarativeBase, mapped_column, relationship


class Base(MappedAsDataclass, DeclarativeBase):  # pyright: ignore[reportUnsafeMultipleInheritance]
    pass


class CardType(StrEnum):
    RULE = "rule"
    TASK = "task"
    POWERUP = "powerup"


class TaskType(StrEnum):
    NORMAL = "normal"
    EXTREME = "extreme"


class TaskSpecial(StrEnum):
    MBS = "mbs"
    FULLERTON = "fullerton"
    NONE = "none"


class PowerupSpecial(StrEnum):
    ALL_OR_NOTHING = "all_or_nothing"
    BUY_1_GET_1_FREE = "buy_1_get_1_free"
    NONE = "none"


class Card(Base, kw_only=True):
    __tablename__: str = "Card"

    card_id: Mapped[int] = mapped_column(primary_key=True, init=False)
    card_type: Mapped[CardType] = mapped_column(init=False)
    image_path: Mapped[str] = mapped_column()

    team_card_joins: Mapped[list[TeamCardJoin]] = relationship(
        back_populates="card",
        cascade="all, delete-orphan",
        init=False,
    )

    # noinspection PyClassVar
    __mapper_args__: ClassVar[dict[str, object]] = {  # pyright: ignore[reportIncompatibleVariableOverride]
        "polymorphic_on": card_type,
        "polymorphic_abstract": True
    }


@final
class RuleCard(Card):
    # noinspection PyClassVar
    __mapper_args__: ClassVar[dict[str, object]] = {
        "polymorphic_identity": CardType.RULE
    }


@final
class TaskCard(Card):
    task_type: Mapped[TaskType] = mapped_column(nullable=True)
    task_special: Mapped[TaskSpecial] = mapped_column(nullable=True)

    # noinspection PyClassVar
    __mapper_args__: ClassVar[dict[str, object]] = {
        "polymorphic_identity": CardType.TASK
    }


@final
class PowerupCard(Card):
    powerup_special: Mapped[PowerupSpecial] = mapped_column(nullable=True)
    powerup_send_to_chasers: Mapped[bool] = mapped_column(nullable=True)

    # noinspection PyClassVar
    __mapper_args__: ClassVar[dict[str, object]] = {
        "polymorphic_identity": CardType.POWERUP
    }


class ChatRole(StrEnum):
    ADMIN = "admin"
    LOCATION = "location"
    TEAM_1 = "team_1"
    TEAM_2 = "team_2"
    TEAM_3 = "team_3"


@final
class GameChat(Base):
    __tablename__ = "Chat"

    chat_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    game_id: Mapped[int] = mapped_column(ForeignKey("Game.game_id"))
    role: Mapped[ChatRole] = mapped_column()
    callback_message_id: Mapped[int | None] = mapped_column(default=None)

    score: Mapped[int | None] = mapped_column(default=None)

    game: Mapped[Game] = relationship(
        foreign_keys=[game_id],
        init=False,
    )
    team_card_joins: Mapped[list[TeamCardJoin]] = relationship(
        back_populates="team_chat",
        cascade="all, delete-orphan",
        init=False,
    )

    def __post_init__(self) -> None:
        if self.score is None and self.role in [ChatRole.TEAM_1, ChatRole.TEAM_2, ChatRole.TEAM_3]:
            self.score = 0

    __table_args__: tuple[Constraint, ...] = (
        UniqueConstraint(game_id, role, name="unique_game_role"),
        CheckConstraint("score IS NULL OR role IN ('TEAM_1', 'TEAM_2', 'TEAM_3')", name="score_only_for_team_chats"),
    )

@final
class Game(Base):
    __tablename__ = "Game"

    game_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    is_started: Mapped[bool] = mapped_column(default=False)
    is_paused: Mapped[bool] = mapped_column(default=False)

    all_or_nothing_active: Mapped[bool] = mapped_column(default=False)
    buy_1_get_1_free_active: Mapped[bool] = mapped_column(default=False)
    buy_1_get_1_free_used: Mapped[bool] = mapped_column(default=False)
    fullerton_early: Mapped[bool | None] = mapped_column(default=None)
    mbs_draw_num: Mapped[int | None] = mapped_column(default=None)

    running_team_chat_id: Mapped[int | None] = mapped_column(ForeignKey("Chat.chat_id"), default=None)

    admin_chat: Mapped[GameChat] = relationship(
        foreign_keys=[game_id],
        primaryjoin=and_(GameChat.game_id == game_id, GameChat.role == ChatRole.ADMIN),
        cascade="all, delete-orphan",
        single_parent=True,
        overlaps="location_chat,team_1_chat,team_2_chat,team_3_chat",
        init=False,
    )
    location_chat: Mapped[GameChat | None] = relationship(
        foreign_keys=[game_id],
        primaryjoin=and_(GameChat.game_id == game_id, GameChat.role == ChatRole.LOCATION),
        cascade="all, delete-orphan",
        single_parent=True,
        overlaps="admin_chat,team_1_chat,team_2_chat,team_3_chat",
        init=False,
    )
    team_1_chat: Mapped[GameChat | None] = relationship(
        foreign_keys=[game_id],
        primaryjoin=and_(GameChat.game_id == game_id, GameChat.role == ChatRole.TEAM_1),
        cascade="all, delete-orphan",
        single_parent=True,
        overlaps="admin_chat,location_chat,team_2_chat,team_3_chat",
        init=False,
    )
    team_2_chat: Mapped[GameChat | None] = relationship(
        foreign_keys=[game_id],
        primaryjoin=and_(GameChat.game_id == game_id, GameChat.role == ChatRole.TEAM_2),
        cascade="all, delete-orphan",
        single_parent=True,
        overlaps="admin_chat,location_chat,team_1_chat,team_3_chat",
        init=False,
    )
    team_3_chat: Mapped[GameChat | None] = relationship(
        foreign_keys=[game_id],
        primaryjoin=and_(GameChat.game_id == game_id, GameChat.role == ChatRole.TEAM_3),
        cascade="all, delete-orphan",
        single_parent=True,
        overlaps="admin_chat,location_chat,team_1_chat,team_2_chat",
        init=False,
    )
    running_team_chat: Mapped[GameChat | None] = relationship(
        foreign_keys=[running_team_chat_id],
        init=False
    )

    __table_args__: tuple[Constraint, ...] = (
        CheckConstraint("NOT is_started OR running_team_chat_id IS NOT NULL"),
    )


class CardState(StrEnum):
    UNDRAWN = "undrawn"
    SHOWN = "shown"
    DRAWN = "drawn"
    PENDING = "pending"  # only for buy 1 get 1 free
    USED = "used"


@final
class TeamCardJoin(Base):
    __tablename__ = "TeamCardJoin"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    team_chat_id: Mapped[int] = mapped_column(ForeignKey("Chat.chat_id", ondelete="CASCADE"))
    card_id: Mapped[int] = mapped_column(ForeignKey("Card.card_id", ondelete="CASCADE"))
    state: Mapped[CardState] = mapped_column()

    team_chat: Mapped[GameChat] = relationship(back_populates="team_card_joins", foreign_keys=[team_chat_id], init=False)
    card: Mapped[Card] = relationship(back_populates="team_card_joins", foreign_keys=[card_id], init=False)

