# movie_bot.py
# Telegram Movie Auto-Detail Bot
#
# IMPORTANT SECURITY WARNING:
# The credentials shown below are EXPOSED and must be revoked immediately.
# 1. Go to @BotFather, use /revoke to reset your bot token
# 2. Go to TMDb settings to regenerate your API key
# 3. Replace the placeholders below with your NEW credentials before running
#
# Setup:
#   pip3 install python-telegram-bot requests
#   python3 movie_bot.py

import os
import re
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)


# ============ CONFIGURATION ============
# Read credentials from environment variables (for security)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8781315448:AAGIUHbCrN2J_22PND6_6wndF8yqrjwiPKo")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "c77cce7316558fb9e7f20586031e9b99")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@Adobopusit2")

if not BOT_TOKEN or not TMDB_API_KEY:
    raise ValueError("❌ Missing required environment variables: BOT_TOKEN and TMDB_API_KEY")

# Optional: OMDB fallback (free tier: 1000 req/day)
# Get key from: http://www.omdbapi.com/apikey.aspx
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")  # Leave empty to skip

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ MOVIE DATABASE APIS ============

class MovieFetcher:
    def __init__(self):
        self.tmdb_base = "https://api.themoviedb.org/3"
        self.tmdb_img_base = "https://image.tmdb.org/t/p/original"
        self.omdb_base = "http://www.omdbapi.com/"
        
    def search_movie(self, title, year=None):
        """Search TMDb for movie details"""
        try:
            params = {
                "api_key": TMDB_API_KEY,
                "query": title,
                "include_adult": "false"
            }
            if year:
                params["year"] = year
                
            response = requests.get(
                f"{self.tmdb_base}/search/movie", 
                params=params, 
                timeout=10
            )
            data = response.json()
            
            if data.get("results"):
                return data["results"][0]
            return None
        except Exception as e:
            logger.error(f"TMDb search error: {e}")
            return None
    
    def get_movie_details(self, movie_id):
        """Get full movie details including credits"""
        try:
            response = requests.get(
                f"{self.tmdb_base}/movie/{movie_id}",
                params={
                    "api_key": TMDB_API_KEY,
                    "append_to_response": "credits,keywords,videos"
                },
                timeout=10
            )
            return response.json()
        except Exception as e:
            logger.error(f"TMDb details error: {e}")
            return None
    
    def get_poster_url(self, poster_path):
        """Construct full poster URL"""
        if not poster_path:
            return None
        return f"{self.tmdb_img_base}{poster_path}"
    
    def fallback_omdb(self, title, year=None):
        """Fallback to OMDB if TMDb fails"""
        if not OMDB_API_KEY:
            return None
        try:
            params = {
                "apikey": OMDB_API_KEY,
                "t": title,
                "type": "movie",
                "plot": "full"
            }
            if year:
                params["y"] = year
            response = requests.get(self.omdb_base, params=params, timeout=10)
            return response.json()
        except Exception as e:
            logger.error(f"OMDb error: {e}")
            return None

movie_fetcher = MovieFetcher()

# ============ TEXT FORMATTING ============

def format_caption(movie_data, source="tmdb"):
    """Format movie data into a beautiful Telegram caption"""
    
    if source == "tmdb":
        title = movie_data.get("title", "Unknown")
        original_title = movie_data.get("original_title", "")
        year = movie_data.get("release_date", "")[:4] if movie_data.get("release_date") else "N/A"
        rating = movie_data.get("vote_average", 0)
        runtime = movie_data.get("runtime", 0)
        overview = movie_data.get("overview", "No description available.")
        genres = [g["name"] for g in movie_data.get("genres", [])]
        
        crew = movie_data.get("credits", {}).get("crew", [])
        directors = [c["name"] for c in crew if c["job"] == "Director"]
        director = ", ".join(directors) if directors else "N/A"
        
        cast = movie_data.get("credits", {}).get("cast", [])[:5]
        cast_names = ", ".join([c["name"] for c in cast]) if cast else "N/A"
        
        stars = "⭐" * int(round(rating / 2)) if rating else "N/A"
        
        hashtags = "#Movie"
        if genres:
            hashtags += " #" + " #".join([g.replace(" ", "") for g in genres[:3]])
        
        caption = f"""🎬 <b>{title}</b> ({year})

📌 <b>Original Title:</b> {original_title}

🎭 <b>Genre:</b> {", ".join(genres) if genres else "N/A"}
⭐ <b>Rating:</b> {rating}/10 {stars}
⏱ <b>Runtime:</b> {runtime} min
🎬 <b>Director:</b> {director}
🎭 <b>Cast:</b> {cast_names}

📝 <b>Synopsis:</b>
{overview[:400]}{"..." if len(overview) > 400 else ""}

{hashtags}
"""
    
    elif source == "omdb":
        title = movie_data.get("Title", "Unknown")
        year = movie_data.get("Year", "N/A")
        rating = movie_data.get("imdbRating", "N/A")
        runtime = movie_data.get("Runtime", "N/A")
        genre = movie_data.get("Genre", "N/A")
        director = movie_data.get("Director", "N/A")
        actors = movie_data.get("Actors", "N/A")
        plot = movie_data.get("Plot", "No description available.")
        
        caption = f"""🎬 <b>{title}</b> ({year})

🎭 <b>Genre:</b> {genre}
⭐ <b>IMDb Rating:</b> {rating}/10
⏱ <b>Runtime:</b> {runtime}
🎬 <b>Director:</b> {director}
🎭 <b>Cast:</b> {actors}

📝 <b>Synopsis:</b>
{plot[:400]}{"..." if len(plot) > 400 else ""}

#Movie #Cinema
"""
    
    return caption

def extract_movie_name(filename):
    """Extract clean movie name from filename"""
    name = os.path.splitext(filename)[0]
    
    patterns = [
        r'\d{3,4}p', r'BluRay', r'WEB[-]?DL', r'WEBRip', r'HDRip', r'DVDRip',
        r'x264', r'x265', r'H264', r'H265', r'HEVC', r'AVC',
        r'AC3', r'AAC', r'DTS', r'HDMA',
        r'YIFY', r'YTS', r'ETRG', r'EVO', r'SPARKS', r'GECKOS', r'RARBG',
        r'\d{4}',
        r'[\[\]\(\)\{\}]',
        r'[._]',
        r'\b(19|20)\d{2}\b'
    ]
    
    clean_name = name
    for pattern in patterns:
        clean_name = re.sub(pattern, ' ', clean_name, flags=re.IGNORECASE)
    
    clean_name = ' '.join(clean_name.split())
    
    year_match = re.search(r'(19|20)\d{2}', name)
    year = year_match.group(0) if year_match else None
    
    return clean_name.strip(), year

# ============ BOT HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    await update.message.reply_text(
        "🎬 <b>Movie Channel Bot</b>\n\n"
        "Upload a movie file and I'll automatically:\n"
        "• Detect the movie title\n"
        "• Fetch details from TMDb/IMDb\n"
        "• Add a poster and formatted caption\n\n"
        "<b>Commands:</b>\n"
        "/setchannel @channel - Set target channel\n"
        "/manual Movie Name - Manually search\n"
        "/skip - Skip auto-processing for next upload",
        parse_mode="HTML"
    )

async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the target channel"""
    global CHANNEL_ID
    if context.args:
        CHANNEL_ID = context.args[0]
        await update.message.reply_text(f"✅ Channel set to: {CHANNEL_ID}")
    else:
        await update.message.reply_text("Usage: /setchannel @channel_username")

async def manual_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually search for a movie"""
    if not context.args:
        await update.message.reply_text("Usage: /manual Movie Name Here")
        return
    
    query = " ".join(context.args)
    await update.message.reply_text(
        f"🔍 Searching for: <b>{query}</b>...", 
        parse_mode="HTML"
    )
    
    result = movie_fetcher.search_movie(query)
    
    if result:
        details = movie_fetcher.get_movie_details(result["id"])
        if details:
            poster_url = movie_fetcher.get_poster_url(details.get("poster_path"))
            caption = format_caption(details, "tmdb")
            
            if poster_url:
                await update.message.reply_photo(
                    photo=poster_url,
                    caption=caption,
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(caption, parse_mode="HTML")
            return
    
    if OMDB_API_KEY:
        omdb_data = movie_fetcher.fallback_omdb(query)
        if omdb_data and omdb_data.get("Response") == "True":
            poster_url = omdb_data.get("Poster")
            caption = format_caption(omdb_data, "omdb")
            
            if poster_url and poster_url != "N/A":
                await update.message.reply_photo(
                    photo=poster_url,
                    caption=caption,
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(caption, parse_mode="HTML")
            return
    
    await update.message.reply_text("❌ Movie not found. Try a different title.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video uploads - Main automation"""
    
    if context.user_data.get("skip_next", False):
        context.user_data["skip_next"] = False
        return
    
    video = update.message.video or update.message.document
    
    if not video:
        return
    
    filename = video.file_name if hasattr(video, 'file_name') else "Unknown"
    movie_name, year = extract_movie_name(filename)
    
    if not movie_name or len(movie_name) < 2:
        await update.message.reply_text(
            "⚠️ Could not detect movie name from filename.\n"
            "Use /manual to search manually."
        )
        return
    
    processing_msg = await update.message.reply_text(
        f"🎬 Detected: <b>{movie_name}</b> {f'({year})' if year else ''}\n"
        f"🔍 Fetching details from TMDb...",
        parse_mode="HTML"
    )
    
    result = movie_fetcher.search_movie(movie_name, year)
    if not result:
        result = movie_fetcher.search_movie(movie_name)
    
    if not result:
        await processing_msg.edit_text(
            "❌ Could not find movie details.\n"
            "Use /manual 'Movie Name' to add details."
        )
        return
    
    details = movie_fetcher.get_movie_details(result["id"])
    
    if not details:
        await processing_msg.edit_text("❌ Error fetching movie details.")
        return
    
    poster_url = movie_fetcher.get_poster_url(details.get("poster_path"))
    caption = format_caption(details, "tmdb")
    
    await processing_msg.delete()
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Send to Channel", callback_data="send"),
            InlineKeyboardButton("🔄 Retry", callback_data="retry")
        ],
        [
            InlineKeyboardButton("✏️ Edit Caption", callback_data="edit"),
            InlineKeyboardButton("❌ Skip", callback_data="skip")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if poster_url:
        preview = await update.message.reply_photo(
            photo=poster_url,
            caption=caption + "\n\n<i>Preview - Click 'Send to Channel' to post</i>",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    else:
        preview = await update.message.reply_text(
            caption + "\n\n<i>Preview - No poster found</i>",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    
    context.user_data["pending_movie"] = {
        "message_id": update.message.message_id,
        "chat_id": update.message.chat_id,
        "caption": caption,
        "poster_url": poster_url,
        "preview_message_id": preview.message_id
    }

async def _edit_preview_message(query, text, parse_mode="HTML"):
    if query.message.photo:
        await query.edit_message_caption(caption=text, parse_mode=parse_mode)
    else:
        await query.edit_message_text(text=text, parse_mode=parse_mode)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "send":
        pending = context.user_data.get("pending_movie")
        if not pending:
            await _edit_preview_message(query, "❌ Session expired. Upload again.")
            return
        
        try:
            if pending.get("poster_url"):
                await context.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=pending["poster_url"],
                    caption=pending["caption"],
                    parse_mode="HTML"
                )
            else:
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=pending["caption"],
                    parse_mode="HTML"
                )
            
            await context.bot.forward_message(
                chat_id=CHANNEL_ID,
                from_chat_id=pending["chat_id"],
                message_id=pending["message_id"]
            )
            
            await _edit_preview_message(
                query,
                "✅ <b>Posted to channel successfully!</b>"
            )
            
        except Exception as e:
            logger.error(f"Send error: {e}")
            await _edit_preview_message(
                query,
                f"❌ Error posting to channel:\n<code>{str(e)}</code>\n\n"
                f"Make sure the bot is admin in {CHANNEL_ID} and can post messages."
            )
    
    elif data == "retry":
        await _edit_preview_message(query, "🔄 Send the movie file again or use /manual")
    
    elif data == "edit":
        await _edit_preview_message(
            query,
            "✏️ <b>Edit Mode</b>\n"
            "Reply to the movie message with:\n"
            "<code>/caption Your new caption here</code>",
            parse_mode="HTML"
        )
    
    elif data == "skip":
        await _edit_preview_message(query, "⏭ Skipped. Upload again when ready.")

async def custom_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom caption"""
    if not context.args:
        await update.message.reply_text("Usage: /caption Your caption text")
        return
    
    custom_text = " ".join(context.args)
    pending = context.user_data.get("pending_movie")
    
    if pending:
        pending["caption"] = custom_text
        await update.message.reply_text(
            "✅ Caption updated! Click 'Send to Channel' in the preview."
        )

async def skip_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skip auto-processing for next upload"""
    context.user_data["skip_next"] = True
    await update.message.reply_text("⏭ Next upload will be skipped from auto-processing.")

# ============ MAIN ============

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setchannel", set_channel))
    application.add_handler(CommandHandler("manual", manual_search))
    application.add_handler(CommandHandler("caption", custom_caption))
    application.add_handler(CommandHandler("skip", skip_next))
    
    application.add_handler(MessageHandler(
        filters.VIDEO | filters.Document.VIDEO | filters.Document.MimeType("video/mp4"),
        handle_video
    ))
    
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 Bot started! Upload a movie file to test.")
    print(f"📺 Target channel: {CHANNEL_ID}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()