from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import Application
import logging
import json
import time

from app.database import get_db, engine
from app.models import Base
from app.telegram_bot import get_bot
from app.crud import get_game_stats, get_active_players, get_leaderboard
from app.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="100 Gates to Freedom Bot",
    description="High-stakes Telegram game with 100 consecutive questions",
    version="2.0.0"
)


@app.on_event("startup")
async def startup_event():
    """Initialize bot webhook on startup"""
    try:
        logger.info("Starting application...")
        
        # Try to initialize database (but don't fail if it's not available)
        try:
            # Wait for database to be ready
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Create database tables
                    Base.metadata.create_all(bind=engine)
                    logger.info("Database tables created successfully")
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
                        time.sleep(2)
                    else:
                        logger.warning(f"Database not available after {max_retries} attempts: {e}")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")
        
        # Initialize bot and set webhook (but don't fail if token is missing)
        try:
            bot = get_bot()
            if bot.application:
                await bot.application.bot.set_webhook(url=f"{settings.webhook_url}/webhook")
                logger.info("Webhook set successfully")
            else:
                logger.warning("Bot not initialized - webhook not set")
        except Exception as e:
            logger.warning(f"Bot initialization failed: {e}")
        
        logger.info("Application startup completed")
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Remove webhook on shutdown"""
    try:
        bot = get_bot()
        if bot.application:
            await bot.application.bot.delete_webhook()
            logger.info("Webhook removed successfully")
    except Exception as e:
        logger.error(f"Failed to remove webhook: {e}")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "100 Gates to Freedom Bot is running!",
        "status": "healthy",
        "version": "2.0.0"
    }


@app.post("/webhook")
async def webhook(request: Request):
    """Telegram webhook endpoint"""
    try:
        bot = get_bot()
        if not bot.application:
            raise HTTPException(status_code=500, detail="Bot not initialized")
            
        # Get update data
        update_data = await request.json()
        update = Update.de_json(update_data, bot.application.bot)
        
        # Process update
        await bot.application.process_update(update)
        
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
async def health_check():
    """Detailed health check"""
    try:
        bot = get_bot()
        return {
            "status": "healthy",
            "bot_token_configured": bool(settings.telegram_bot_token),
            "bot_initialized": bool(bot.application),
            "database_configured": bool(settings.database_url),
            "webhook_url": settings.webhook_url
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# Admin endpoints
def verify_admin(telegram_id: int):
    """Verify if user is admin"""
    if telegram_id not in settings.admin_telegram_ids:
        raise HTTPException(status_code=403, detail="Admin access required")


@app.get("/admin/stats")
async def admin_stats(
    telegram_id: int,
    db: Session = Depends(get_db)
):
    """Get game statistics (admin only)"""
    verify_admin(telegram_id)
    
    try:
        stats = get_game_stats(db)
        return stats
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/admin/players")
async def admin_players(
    telegram_id: int,
    db: Session = Depends(get_db)
):
    """Get all active players (admin only)"""
    verify_admin(telegram_id)
    
    try:
        players = get_active_players(db)
        return [
            {
                "telegram_id": player.telegram_id,
                "username": player.username,
                "current_gate": player.current_gate,
                "start_time": player.start_time.isoformat(),
                "last_activity": player.last_activity.isoformat()
            }
            for player in players
        ]
    except Exception as e:
        logger.error(f"Error getting players: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/admin/leaderboard")
async def admin_leaderboard(
    telegram_id: int,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get leaderboard (admin only)"""
    verify_admin(telegram_id)
    
    try:
        leaderboard = get_leaderboard(db, limit=limit)
        return [
            {
                "telegram_id": player.telegram_id,
                "username": player.username,
                "current_gate": player.current_gate,
                "game_state": player.game_state.value,
                "start_time": player.start_time.isoformat(),
                "completed_at": player.completed_at.isoformat() if player.completed_at else None
            }
            for player in leaderboard
        ]
    except Exception as e:
        logger.error(f"Error getting leaderboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/admin/reset-game")
async def admin_reset_game(
    telegram_id: int,
    db: Session = Depends(get_db)
):
    """Reset all games globally (admin only)"""
    verify_admin(telegram_id)
    
    try:
        # Reset all players to eliminated state
        db.execute("UPDATE players SET game_state = 'eliminated', current_gate = 1")
        db.execute("UPDATE games SET status = 'failed'")
        db.commit()
        
        return {"message": "Game reset successfully"}
    except Exception as e:
        logger.error(f"Error resetting game: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 