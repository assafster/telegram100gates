from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.models import GameState, EliminationReason, GameStatus


class PlayerBase(BaseModel):
    telegram_id: int
    username: Optional[str] = None


class PlayerCreate(PlayerBase):
    pass


class Player(PlayerBase):
    id: int
    current_gate: int
    game_state: GameState
    elimination_reason: Optional[EliminationReason]
    start_time: datetime
    last_activity: datetime
    completed_at: Optional[datetime]
    
    class Config:
        orm_mode = True


class QuestionBase(BaseModel):
    gate_number: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str


class QuestionCreate(QuestionBase):
    pass


class Question(QuestionBase):
    id: int
    
    class Config:
        orm_mode = True


class GameBase(BaseModel):
    player_id: int
    gate_number: int
    question_id: int
    timeout_at: datetime


class GameCreate(GameBase):
    pass


class Game(GameBase):
    id: int
    start_time: datetime
    status: GameStatus
    
    class Config:
        orm_mode = True


class TelegramUpdate(BaseModel):
    update_id: int
    message: Optional[dict] = None
    callback_query: Optional[dict] = None


class TelegramMessage(BaseModel):
    message_id: int
    from_user: dict
    chat: dict
    date: int
    text: Optional[str] = None


class TelegramCallbackQuery(BaseModel):
    id: str
    from_user: dict
    message: dict
    data: str


class LeaderboardEntry(BaseModel):
    telegram_id: int
    username: Optional[str]
    current_gate: int
    game_state: GameState
    start_time: datetime


class GameStats(BaseModel):
    total_players: int
    active_players: int
    eliminated_players: int
    completed_players: int
    average_gate: float
    dropoff_by_gate: dict 