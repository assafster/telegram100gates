import logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from sqlalchemy.orm import Session
from app.database import get_db
from app.crud import (
    start_new_game, get_player, check_answer, get_question, 
    eliminate_player, get_leaderboard, get_game_stats
)
from app.models import GameState, EliminationReason, Game, GameStatus
from app.config import settings
import asyncio
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):
        try:
            self.application = Application.builder().token(settings.telegram_bot_token).build()
            self.setup_handlers()
            logger.info("Telegram bot initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            self.application = None
    
    def setup_handlers(self):
        """Setup all command and callback handlers"""
        if not self.application:
            return
            
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("restart", self.restart_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("leaderboard", self.leaderboard_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        telegram_id = update.effective_user.id
        username = update.effective_user.username
        
        # Get database session
        db = next(get_db())
        try:
            # Start new game
            player = start_new_game(db, telegram_id, username)
            
            # Get first question
            question = get_question(db, 1)
            if not question:
                await update.message.reply_text("❌ Game not ready. Please contact admin.")
                return
            
            # Send welcome message and first question
            welcome_text = (
                "🎮 **100 Gates to Freedom**\n\n"
                "🏆 **Prize**: 69% of the reward pool to the first winner!\n"
                "⚡ **Rules**: Answer 100 questions correctly in a row\n"
                "⏱ **Timer**: 30 seconds per question\n"
                "💀 **One Strike**: Wrong answer or timeout = game over\n\n"
                "🚪 **Gate 1 of 100**\n\n"
                f"❓ {question.question_text}"
            )
            
            keyboard = self.create_answer_keyboard()
            await update.message.reply_text(
                welcome_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await update.message.reply_text("❌ An error occurred. Please try again.")
        finally:
            db.close()
    
    async def restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /restart command"""
        await self.start_command(update, context)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "🎮 **100 Gates to Freedom - Game Rules**\n\n"
            "**Objective**: Be the first to answer 100 questions correctly!\n\n"
            "**How to Play**:\n"
            "• Each question is a 'gate' you must pass\n"
            "• You have 30 seconds to answer each question\n"
            "• Choose from 4 multiple-choice options (A, B, C, D)\n"
            "• One wrong answer or timeout = game over\n"
            "• Start over from Gate 1 if you fail\n\n"
            "**Commands**:\n"
            "• `/start` - Begin new game\n"
            "• `/restart` - Reset and start over\n"
            "• `/status` - Check your progress\n"
            "• `/leaderboard` - View top players\n"
            "• `/help` - Show this help\n\n"
            "**Prize**: 69% of the reward pool to the first winner! 🏆\n\n"
            "Good luck! May the fastest mind win! 🚀"
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        telegram_id = update.effective_user.id
        
        db = next(get_db())
        try:
            player = get_player(db, telegram_id)
            
            if not player:
                await update.message.reply_text(
                    "❌ You haven't started a game yet. Use `/start` to begin!",
                    parse_mode='Markdown'
                )
                return
            
            if player.game_state == GameState.ACTIVE:
                status_text = (
                    f"🎮 **Your Game Status**\n\n"
                    f"🚪 **Current Gate**: {player.current_gate}/100\n"
                    f"⏱ **Started**: {player.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"🔄 **Status**: Active\n\n"
                    f"Keep going! You're doing great! 💪"
                )
            elif player.game_state == GameState.ELIMINATED:
                reason = "Timeout" if player.elimination_reason == EliminationReason.TIMEOUT else "Wrong Answer"
                status_text = (
                    f"💀 **Game Over**\n\n"
                    f"🚪 **Failed at Gate**: {player.current_gate}/100\n"
                    f"❌ **Reason**: {reason}\n\n"
                    f"Use `/start` to try again! 🔄"
                )
            else:  # COMPLETED
                status_text = (
                    f"🏆 **Congratulations!**\n\n"
                    f"You've completed all 100 gates!\n"
                    f"🎉 **Completed**: {player.completed_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"You're a winner! 🎊"
                )
            
            await update.message.reply_text(status_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await update.message.reply_text("❌ An error occurred. Please try again.")
        finally:
            db.close()
    
    async def leaderboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /leaderboard command"""
        db = next(get_db())
        try:
            leaderboard = get_leaderboard(db, limit=10)
            
            if not leaderboard:
                await update.message.reply_text("📊 No players yet. Be the first to start!")
                return
            
            leaderboard_text = "🏆 **Top Players**\n\n"
            
            for i, player in enumerate(leaderboard, 1):
                username = player.username or f"Player{player.telegram_id}"
                status_emoji = "🟢" if player.game_state == GameState.ACTIVE else "🔴"
                leaderboard_text += f"{i}. {status_emoji} @{username} - Gate {player.current_gate}/100\n"
            
            leaderboard_text += "\nUse `/start` to join the competition! 🚀"
            
            await update.message.reply_text(leaderboard_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in leaderboard command: {e}")
            await update.message.reply_text("❌ An error occurred. Please try again.")
        finally:
            db.close()
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks (answer selections)"""
        query = update.callback_query
        await query.answer()
        
        telegram_id = update.effective_user.id
        answer = query.data
        
        db = next(get_db())
        try:
            player = get_player(db, telegram_id)
            
            if not player or player.game_state != GameState.ACTIVE:
                await query.edit_message_text(
                    "❌ Your game is not active. Use `/start` to begin!",
                    parse_mode='Markdown'
                )
                return
            
            # Check if answer is correct
            is_correct = check_answer(db, telegram_id, answer)
            
            if is_correct:
                # Check if player completed the game
                updated_player = get_player(db, telegram_id)
                if updated_player.game_state == GameState.COMPLETED:
                    # WINNER!
                    await query.edit_message_text(
                        "🏆 **CONGRATULATIONS!** 🏆\n\n"
                        "🎉 You've completed all 100 gates!\n"
                        "💰 You've won 69% of the prize pool!\n\n"
                        "You are the first winner of 100 Gates to Freedom!\n"
                        "Contact admin for your prize! 🎊",
                        parse_mode='Markdown'
                    )
                else:
                    # Get next question
                    next_question = get_question(db, updated_player.current_gate)
                    if next_question:
                        question_text = (
                            f"✅ **Gate {player.current_gate} Unlocked!**\n\n"
                            f"🚪 **Gate {updated_player.current_gate} of 100**\n\n"
                            f"❓ {next_question.question_text}"
                        )
                        
                        keyboard = self.create_answer_keyboard()
                        await query.edit_message_text(
                            question_text,
                            reply_markup=keyboard,
                            parse_mode='Markdown'
                        )
                    else:
                        await query.edit_message_text(
                            "❌ Error loading next question. Please contact admin.",
                            parse_mode='Markdown'
                        )
            else:
                # Wrong answer - player eliminated
                reason = "Wrong Answer"
                await query.edit_message_text(
                    f"❌ **Wrong Answer!**\n\n"
                    f"💀 You've been eliminated at Gate {player.current_gate}.\n"
                    f"🔙 Back to Gate 1 you go!\n\n"
                    f"Use `/start` to try again! 🔄",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Error in callback handler: {e}")
            await query.edit_message_text(
                "❌ An error occurred. Please try again.",
                parse_mode='Markdown'
            )
        finally:
            db.close()
    
    def create_answer_keyboard(self) -> InlineKeyboardMarkup:
        """Create inline keyboard with answer options"""
        keyboard = [
            [
                InlineKeyboardButton("A", callback_data="A"),
                InlineKeyboardButton("B", callback_data="B"),
                InlineKeyboardButton("C", callback_data="C"),
                InlineKeyboardButton("D", callback_data="D")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def check_timeouts(self):
        """Background task to check for expired games"""
        while True:
            try:
                db = next(get_db())
                expired_games = db.query(Game).filter(
                    Game.status == GameStatus.ACTIVE,
                    Game.timeout_at < datetime.utcnow()
                ).all()
                
                for game in expired_games:
                    # Eliminate player due to timeout
                    player = get_player(db, game.player_id)
                    if player and player.game_state == GameState.ACTIVE:
                        eliminate_player(db, game.player_id, EliminationReason.TIMEOUT)
                        
                        # Update game status
                        game.status = GameStatus.FAILED
                        db.commit()
                        
                        # Send timeout message (this would need to be implemented with bot context)
                        logger.info(f"Player {player.telegram_id} timed out at gate {player.current_gate}")
                
                db.close()
                
            except Exception as e:
                logger.error(f"Error in timeout checker: {e}")
            
            # Check every 5 seconds
            await asyncio.sleep(5)
    
    def run(self):
        """Start the bot"""
        # Start timeout checker in background
        asyncio.create_task(self.check_timeouts())
        
        # Start the bot
        self.application.run_polling()


# Global bot instance - initialize lazily
bot = None

def get_bot():
    """Get or create bot instance"""
    global bot
    if bot is None:
        bot = TelegramBot()
    return bot 