import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from . import config


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class GameStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    ENDED = "ended"


class TeamInstanceStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    ERROR = "error"
    DESTROYED = "destroyed"


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    password_salt: Mapped[str] = mapped_column(String(64))
    # Generated once at registration (secrets.token_hex(32)), never shown
    # to anyone, never regenerated -- the root of every flag this team
    # will ever derive. No endpoint anywhere reads or writes this after
    # creation except the internal call to the orchestrator.
    team_secret: Mapped[str] = mapped_column(String(64))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    solves: Mapped[list["Solve"]] = relationship(back_populates="team")
    instances: Mapped[list["TeamInstance"]] = relationship(back_populates="team")


class Admin(Base):
    """Deliberately a separate table from Team, not an is_admin flag --
    see the plan's Decisions section: an is_admin flag on Team would mean
    every team-listing query (scoreboard, admin team view, CSV export)
    must remember to filter it out, forever. An admin account has no
    team-shaped fields anyway (no team_secret, no scoreboard entry, no
    orchestrator instances)."""

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    password_salt: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[GameStatus] = mapped_column(Enum(GameStatus), default=GameStatus.DRAFT)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # App-level invariant (enforced in services/games.py, not the DB):
    # at most one Game with status=RUNNING at a time.

    challenges: Mapped[list["Challenge"]] = relationship(back_populates="game", cascade="all, delete-orphan")


class Challenge(Base):
    __tablename__ = "challenges"
    __table_args__ = (UniqueConstraint("game_id", "box_id", "flag_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), index=True)
    # Validated against boxes_catalog.py's static list of known box_ids,
    # not a DB-level foreign key -- the orchestrator owns that list.
    box_id: Mapped[str] = mapped_column(String(128))
    flag_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(128))
    points: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    game: Mapped[Game] = relationship(back_populates="challenges")
    solves: Mapped[list["Solve"]] = relationship(back_populates="challenge")


class Submission(Base):
    """Full audit log of every flag-submission attempt, correct or not --
    admin visibility into abuse/brute-forcing, honest audit trail. NOT
    what scoring/duplicate-checks query -- see Solve for that."""

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"), index=True)
    challenge_id: Mapped[int] = mapped_column(Integer, ForeignKey("challenges.id"), index=True)
    submitted_value: Mapped[str] = mapped_column(String(256))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Solve(Base):
    """The authoritative 'already solved' + scoring source. UNIQUE on
    (team_id, challenge_id) is the real duplicate-resubmit guard;
    SUM(Challenge.points) JOIN Solve gives O(1) scoreboard computation
    with no need to ever scan the full Submission log."""

    __tablename__ = "solves"
    __table_args__ = (UniqueConstraint("team_id", "challenge_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"), index=True)
    challenge_id: Mapped[int] = mapped_column(Integer, ForeignKey("challenges.id"), index=True)
    submission_id: Mapped[int] = mapped_column(Integer, ForeignKey("submissions.id"))
    solved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    team: Mapped[Team] = relationship(back_populates="solves")
    challenge: Mapped[Challenge] = relationship(back_populates="solves")


class TeamInstance(Base):
    """Local cache mirroring orchestrator state. Not a hard unique
    constraint on (team_id, box_id) -- the orchestrator is already
    idempotent there; worst case of a local race is one harmless extra
    GET against it."""

    __tablename__ = "team_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # = orchestrator's instance_id
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"), index=True)
    box_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[TeamInstanceStatus] = mapped_column(Enum(TeamInstanceStatus), default=TeamInstanceStatus.PENDING)
    entry_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entry_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # [{service_name, container_port, host_port, protocol}] -- populated
    # once the orchestrator's Phase-B ports-field patch lands; None until
    # then, UI falls back to entry_host/entry_port only.
    ports: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    team: Mapped[Team] = relationship(back_populates="instances")


_engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(_engine)


def get_session() -> Session:
    return SessionLocal()
