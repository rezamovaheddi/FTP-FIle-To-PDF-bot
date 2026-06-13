import logging
import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BACKEND_URL = "http://localhost:8000"
TELEGRAM_BOT_TOKEN = "8737722275:AAEyh9fM0pzAU4F22CsXQ0h9R7dZ4k-nn1c"   


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    await update.message.reply_text(
        "🤖 Welcome to File-to-PDF Converter!\n\n"
        "Send me any file and I'll convert it to PDF for you.\n\n"
        "📋 Available Commands:\n"
        "/start - Show this welcome message\n"
        "/last - View your last 5 conversions\n\n"
        "📤 Just upload any file to get started!"
    )

async def last_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /last command"""
    user_id = str(update.effective_user.id)
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/last/{user_id}",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        conversions = data.get("conversions", [])
        if not conversions:
            await update.message.reply_text(
                "📭 No previous conversions found.\n"
                "Send me a file to start converting!"
            )
            return
        
        message = "📜 Your Last 5 Conversions:\n\n"
        for i, conversion in enumerate(conversions, 1):
            date_str = conversion.get('date', 'Unknown').split('T')[0]
            message += f"{i}. {conversion['original_file']}\n"
            message += f"   📅 {date_str}\n"
        
        await update.message.reply_text(message)
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching last conversions: {e}")
        await update.message.reply_text(
            "❌ Error retrieving conversions. Please try again later."
        )
    except Exception as e:
        logger.error(f"Unexpected error in last_command: {e}")
        await update.message.reply_text(
            "❌ An unexpected error occurred. Please try again."
        )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle file uploads"""
    user_id = str(update.effective_user.id)
    
    if not update.message.document:
        await update.message.reply_text("❌ Please send a valid file.")
        return
    
    file_obj = update.message.document
    original_filename = file_obj.file_name or "file"
    
    # Send immediate status message
    processing_msg = await update.message.reply_text(
        "Your file is being converted to PDF… Please wait ⏳"
    )
    
    temp_file_path = None
    try:
        # Download file from Telegram
        tg_file = await context.bot.get_file(file_obj.file_id)
        temp_file_path = f"temp_{file_obj.file_id}_{original_filename}"
        await tg_file.download_to_drive(temp_file_path)
        
        # Send to backend
        with open(temp_file_path, 'rb') as f:
            files = {'file': (original_filename, f)}
            data = {'user_id': user_id}
            response = requests.post(
                f"{BACKEND_URL}/convert",
                files=files,
                data=data,
                timeout=30
            )
        
        response.raise_for_status()
        result = response.json()
        pdf_file_path = result.get('pdf_file')
        
        if not pdf_file_path:
            raise ValueError("No PDF file path returned from backend")
        
        # Download PDF from backend
        pdf_response = requests.get(
            f"{BACKEND_URL}/pdf",
            params={"file_path": pdf_file_path},
            timeout=30
        )
        pdf_response.raise_for_status()
        
        # Edit the processing message to show success
        await processing_msg.edit_text("Your PDF is ready! 🎉")
        
        # Send PDF to user
        pdf_filename = os.path.splitext(original_filename)[0] + ".pdf"
        await update.message.reply_document(
            document=pdf_response.content,
            filename=pdf_filename
        )
    
    except requests.exceptions.Timeout:
        logger.error(f"Timeout during file processing for user {user_id}")
        await processing_msg.edit_text(
            "❌ Request timed out. Please try with a smaller file."
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        await processing_msg.edit_text(
            "❌ Cannot connect to conversion service. Is the backend running on port 8000?"
        )
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error during file processing: {e}")
        error_detail = "Backend service error"
        if e.response.status_code == 404:
            error_detail = "Conversion service not found. Is backend running?"
        elif e.response.status_code == 500:
            error_detail = "Backend processing error. Check backend logs."
        await processing_msg.edit_text(
            f"❌ Conversion failed ({e.response.status_code}). {error_detail}"
        )
    except Exception as e:
        logger.error(f"Error processing file for user {user_id}: {e}")
        await processing_msg.edit_text(
            f"❌ Error converting file: {str(e)[:100]}"
        )
    
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                logger.error(f"Error removing temp file: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject text messages"""
    await update.message.reply_text(
        "📄 Please send a file to convert to PDF.\n\n"
        "Commands:\n"
        "/start - Get help\n"
        "/last - View your conversions"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main() -> None:
    """Start the bot"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("last", last_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text
    ))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()