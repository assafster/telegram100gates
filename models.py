from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class GameState(enum.Enum):
    ACTIVE = "active"
    ELIMINATED = "eliminated"
    COMPLETED = "completed"


class EliminationReason(enum.Enum):
    TIMEOUT = "timeout"
    WRONG_ANSWER = "wrong_answer"


class GameStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    current_gate = Column(Integer, default=1)
    game_state = Column(Enum(GameState), default=GameState.ACTIVE)
    elimination_reason = Column(Enum(EliminationReason), nullable=True)
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    games = relationship("Game", back_populates="player")


class Game(Base):
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    gate_number = Column(Integer, nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    timeout_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(GameStatus), default=GameStatus.ACTIVE)
    
    # Relationships
    player = relationship("Player", back_populates="games")
    question = relationship("Question")


class Question(Base):
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    gate_number = Column(Integer, unique=True, nullable=False)
    question_text = Column(Text, nullable=False)
    option_a = Column(String, nullable=False)
    option_b = Column(String, nullable=False)
    option_c = Column(String, nullable=False)
    option_d = Column(String, nullable=False)
    correct_answer = Column(String(1), nullable=False)  # A, B, C, or D 