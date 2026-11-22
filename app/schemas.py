from datetime import datetime

from pydantic import BaseModel, field_validator

from .models import GameStatus, TeamInstanceStatus


class TeamRegisterRequest(BaseModel):
    name: str
    password: str
    confirm_password: str
    # Anti-abuse fields -- see api/auth.py for how these are checked.
    # website: honeypot, must stay empty; a bot's generic form-filler is
    # the one thing expected to populate it.
    website: str = ""
    form_token: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 64):
            raise ValueError("team name must be 1-64 characters")
        return v

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class TeamLoginRequest(BaseModel):
    name: str
    password: str


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class TeamResponse(BaseModel):
    id: int
    name: str
    disabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class GameCreateRequest(BaseModel):
    name: str
    start_at: datetime | None = None
    end_at: datetime | None = None


class GameResponse(BaseModel):
    id: int
    name: str
    status: GameStatus
    start_at: datetime | None
    end_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class ChallengeCreateRequest(BaseModel):
    box_id: str
    flag_number: int
    title: str
    points: int
    description: str | None = None

    @field_validator("flag_number")
    @classmethod
    def flag_number_range(cls, v: int) -> int:
        if not (1 <= v <= 10):
            raise ValueError("flag_number must be 1-10")
        return v


class ChallengeResponse(BaseModel):
    id: int
    game_id: int
    box_id: str
    flag_number: int
    title: str
    points: int
    description: str | None

    class Config:
        from_attributes = True


class ChallengeWithSolveResponse(BaseModel):
    id: int
    game_id: int
    box_id: str
    flag_number: int
    title: str
    points: int
    description: str | None
    solved: bool


class SubmissionRequest(BaseModel):
    challenge_id: int
    value: str


class SubmissionResult(BaseModel):
    correct: bool
    already_solved: bool = False


class TeamInstanceResponse(BaseModel):
    id: str
    team_id: int
    box_id: str
    status: TeamInstanceStatus
    entry_host: str | None
    entry_port: int | None
    ports: list | None
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class StartInstanceRequest(BaseModel):
    box_id: str


class RenewInstanceRequest(BaseModel):
    extra_minutes: int
