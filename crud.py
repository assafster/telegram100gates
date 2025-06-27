from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timedelta
from app.models import Player, Question, Game, GameState, EliminationReason, GameStatus
from app.schemas import PlayerCreate, QuestionCreate
from app.config import settings


# Player CRUD operations
def get_player(db: Session, telegram_id: int) -> Optional[Player]:
    return db.query(Player).filter(Player.telegram_id == telegram_id).first()


def create_player(db: Session, player: PlayerCreate) -> Player:
    db_player = Player(**player.dict())
    db.add(db_player)
    db.commit()
    db.refresh(db_player)
    return db_player


def update_player(db: Session, telegram_id: int, **kwargs) -> Optional[Player]:
    player = get_player(db, telegram_id)
    if player:
        for key, value in kwargs.items():
            setattr(player, key, value)
        db.commit()
        db.refresh(player)
    return player


def get_active_players(db: Session) -> List[Player]:
    return db.query(Player).filter(Player.game_state == GameState.ACTIVE).all()


def get_leaderboard(db: Session, limit: int = 10) -> List[Player]:
    return db.query(Player).order_by(desc(Player.current_gate)).limit(limit).all()


# Question CRUD operations
def get_question(db: Session, gate_number: int) -> Optional[Question]:
    return db.query(Question).filter(Question.gate_number == gate_number).first()


def create_question(db: Session, question: QuestionCreate) -> Question:
    db_question = Question(**question.dict())
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    return db_question


def get_all_questions(db: Session) -> List[Question]:
    return db.query(Question).order_by(Question.gate_number).all()


# Game CRUD operations
def create_game(db: Session, player_id: int, gate_number: int, question_id: int) -> Game:
    timeout_at = datetime.utcnow() + timedelta(seconds=settings.question_timeout)
    db_game = Game(
        player_id=player_id,
        gate_number=gate_number,
        question_id=question_id,
        timeout_at=timeout_at
    )
    db.add(db_game)
    db.commit()
    db.refresh(db_game)
    return db_game


def get_active_game(db: Session, player_id: int) -> Optional[Game]:
    return db.query(Game).filter(
        Game.player_id == player_id,
        Game.status == GameStatus.ACTIVE
    ).first()


def update_game_status(db: Session, game_id: int, status: GameStatus) -> Optional[Game]:
    game = db.query(Game).filter(Game.id == game_id).first()
    if game:
        game.status = status
        db.commit()
        db.refresh(game)
    return game


def get_expired_games(db: Session) -> List[Game]:
    return db.query(Game).filter(
        Game.status == GameStatus.ACTIVE,
        Game.timeout_at < datetime.utcnow()
    ).all()


# Game logic operations
def start_new_game(db: Session, telegram_id: int, username: str = None) -> Player:
    """Start a new game for a player"""
    player = get_player(db, telegram_id)
    
    if not player:
        # Create new player
        player = create_player(db, PlayerCreate(telegram_id=telegram_id, username=username))
    else:
        # Reset existing player
        player.current_gate = 1
        player.game_state = GameState.ACTIVE
        player.elimination_reason = None
        player.start_time = datetime.utcnow()
        player.completed_at = None
        db.commit()
        db.refresh(player)
    
    # Create first game session
    question = get_question(db, 1)
    if question:
        create_game(db, player.id, 1, question.id)
    
    return player


def advance_gate(db: Session, telegram_id: int) -> Optional[Player]:
    """Advance player to next gate"""
    player = get_player(db, telegram_id)
    if not player or player.game_state != GameState.ACTIVE:
        return None
    
    # Check if player completed the game
    if player.current_gate >= settings.total_gates:
        player.game_state = GameState.COMPLETED
        player.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(player)
        return player
    
    # Advance to next gate
    player.current_gate += 1
    
    # Create new game session for next gate
    question = get_question(db, player.current_gate)
    if question:
        create_game(db, player.id, player.current_gate, question.id)
    
    db.commit()
    db.refresh(player)
    return player


def eliminate_player(db: Session, telegram_id: int, reason: EliminationReason) -> Optional[Player]:
    """Eliminate player from the game"""
    player = get_player(db, telegram_id)
    if not player:
        return None
    
    player.game_state = GameState.ELIMINATED
    player.elimination_reason = reason
    
    # Mark current game as failed
    active_game = get_active_game(db, player.id)
    if active_game:
        update_game_status(db, active_game.id, GameStatus.FAILED)
    
    db.commit()
    db.refresh(player)
    return player


def check_answer(db: Session, telegram_id: int, answer: str) -> bool:
    """Check if player's answer is correct"""
    player = get_player(db, telegram_id)
    if not player or player.game_state != GameState.ACTIVE:
        return False
    
    active_game = get_active_game(db, player.id)
    if not active_game or active_game.timeout_at < datetime.utcnow():
        return False
    
    question = active_game.question
    is_correct = question.correct_answer.upper() == answer.upper()
    
    if is_correct:
        # Mark current game as completed
        update_game_status(db, active_game.id, GameStatus.COMPLETED)
        # Advance to next gate
        advance_gate(db, telegram_id)
    else:
        # Eliminate player
        eliminate_player(db, telegram_id, EliminationReason.WRONG_ANSWER)
    
    return is_correct


def get_game_stats(db: Session) -> dict:
    """Get game statistics"""
    total_players = db.query(Player).count()
    active_players = db.query(Player).filter(Player.game_state == GameState.ACTIVE).count()
    eliminated_players = db.query(Player).filter(Player.game_state == GameState.ELIMINATED).count()
    completed_players = db.query(Player).filter(Player.game_state == GameState.COMPLETED).count()
    
    # Calculate average gate
    avg_gate_result = db.query(func.avg(Player.current_gate)).scalar()
    average_gate = float(avg_gate_result) if avg_gate_result else 0.0
    
    # Calculate dropoff by gate
    dropoff_by_gate = {}
    for gate in range(1, settings.total_gates + 1):
        eliminated_at_gate = db.query(Player).filter(
            Player.current_gate == gate,
            Player.game_state == GameState.ELIMINATED
        ).count()
        dropoff_by_gate[gate] = eliminated_at_gate
    
    return {
        "total_players": total_players,
        "active_players": active_players,
        "eliminated_players": eliminated_players,
        "completed_players": completed_players,
        "average_gate": average_gate,
        "dropoff_by_gate": dropoff_by_gate
    } 