import os
import logging
import sqlite3
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8253205115:AAFrPW7aAtJ8LdxyvjtTythTalvkn4FSuCk")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5573149859"))
CHANNEL_USERNAME = "@wbrand_shop"
CHANNEL_LINK = "https://t.me/wbrand_shop"
TELEBIRR_NUMBER = "0940213338"
PREMIUM_PRICE = "30 Birr / 7 Days"
FREE_DAILY_LIMIT = 3

logging.basicConfig(level=logging.INFO)

# ================= DATABASE =================
db = sqlite3.connect("users.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    is_premium INTEGER DEFAULT 0,
    premium_until TEXT,
    captcha_passed INTEGER DEFAULT 0,
    free_used_today INTEGER DEFAULT 0,
    last_used TEXT,
    language TEXT DEFAULT 'english'
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS payments (
    user_id INTEGER,
    username TEXT,
    screenshot_file_id TEXT,
    status TEXT
)
""")
db.commit()

# ================= HELPERS =================
def is_premium(user_id):
    cur.execute("SELECT premium_until FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        return False
    return datetime.now() < datetime.fromisoformat(row[0])

def set_premium(user_id):
    expiry = datetime.now() + timedelta(days=7)
    cur.execute(
        "UPDATE users SET is_premium=1, premium_until=? WHERE user_id=?",
        (expiry.isoformat(), user_id)
    )
    db.commit()

def can_use_free(user_id):
    cur.execute("SELECT free_used_today, last_used FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        return True
    used, last = row
    if not last or datetime.now().date() != datetime.fromisoformat(last).date():
        cur.execute("UPDATE users SET free_used_today=0, last_used=? WHERE user_id=?", (datetime.now().isoformat(), user_id))
        db.commit()
        return True
    return used < FREE_DAILY_LIMIT

def increment_free_usage(user_id):
    cur.execute("SELECT free_used_today FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    used = row[0] if row else 0
    used += 1
    cur.execute("UPDATE users SET free_used_today=?, last_used=? WHERE user_id=?", (used, datetime.now().isoformat(), user_id))
    db.commit()

def get_user_language(user_id):
    cur.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 'english'

def set_user_language(user_id, language):
    cur.execute("UPDATE users SET language=? WHERE user_id=?", (language, user_id))
    db.commit()

# ================= CAPTCHA =================
async def captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    db.commit()
    keyboard = [[
        InlineKeyboardButton("7", callback_data="cap_wrong"),
        InlineKeyboardButton("11", callback_data="cap_ok")
    ]]
    await update.message.reply_text(
        "🤖 CAPTCHA\n\nWhat is 5 + 6 ?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def captcha_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "cap_ok":
        cur.execute("UPDATE users SET captcha_passed=1 WHERE user_id=?", (q.from_user.id,))
        db.commit()
        await q.edit_message_text("✅ Captcha passed! Use /start again.")
    else:
        await q.answer("❌ Wrong answer", show_alert=True)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    db.commit()

    cur.execute("SELECT captcha_passed FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row or row[0] == 0:
        await captcha(update, context)
        return

    # Check if user joined channel
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ["member", "creator", "administrator"]:
            # Show language selection
            keyboard = [
                [InlineKeyboardButton("🇬🇧 English", callback_data="lang_english")],
                [InlineKeyboardButton("🇪🇹 Amharic", callback_data="lang_amharic")],
                [InlineKeyboardButton("🇪🇹 Afan Oromo", callback_data="lang_oromo")],
                [InlineKeyboardButton("🇪🇹 Tigrigna", callback_data="lang_tigrigna")]
            ]
            
            await update.message.reply_text(
                "🌍 **Select your language:**\n\n"
                "Choose the language for your PDF documents:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
    except Exception as e:
        print(f"Error checking channel: {e}")

    # If not joined, show join message
    join_message = """Hello 💤,

You need to join in my main Channel to use me.

Kindly Please join Channel.

📍 TRY AGAIN"""
    
    keyboard = [
        [InlineKeyboardButton("🔗 Join Channel", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ I Joined", callback_data="check_join")]
    ]
    
    await update.message.reply_text(
        join_message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= CHECK JOIN CALLBACK =================
async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    
    # Delete the old message
    try:
        await q.message.delete()
    except:
        pass
    
    # Check if user joined
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        
        if member.status in ["member", "creator", "administrator"]:
            # Show language selection
            keyboard = [
                [InlineKeyboardButton("🇬🇧 English", callback_data="lang_english")],
                [InlineKeyboardButton("🇪🇹 Amharic", callback_data="lang_amharic")],
                [InlineKeyboardButton("🇪🇹 Afan Oromo", callback_data="lang_oromo")],
                [InlineKeyboardButton("🇪🇹 Tigrigna", callback_data="lang_tigrigna")]
            ]
            
            await q.message.reply_text(
                "✅ **Thank you for joining!**\n\n"
                "🌍 **Now select your language:**\n"
                "Choose the language for your PDF documents:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
    except Exception as e:
        print(f"Error checking channel: {e}")
    
    # If not joined, show join message again
    join_message = """Hello 💤,

You need to join in my main Channel to use me.

Kindly Please join Channel.

📍 TRY AGAIN"""
    
    keyboard = [
        [InlineKeyboardButton("🔗 Join Channel", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ I Joined", callback_data="check_join")]
    ]
    
    await q.message.reply_text(
        join_message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= LANGUAGE SELECTION =================
async def language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    language = q.data.replace("lang_", "")
    
    set_user_language(user_id, language)
    
    lang_names = {
        'english': 'English',
        'amharic': 'Amharic',
        'oromo': 'Afan Oromo',
        'tigrigna': 'Tigrigna'
    }
    
    keyboard = [
        [InlineKeyboardButton("✅ YES (Premium)", callback_data="premium_choice")],
        [InlineKeyboardButton("❌ NO (Free Mode)", callback_data="free_choice")]
    ]
    
    await q.edit_message_text(
        f"✅ Language set to: {lang_names[language]}\n\n"
        f"❓ Do you want Premium? Weekly 30 Birr – Unlimited\n\n"
        f"Free: 3 PDFs per day\n"
        f"Premium: Unlimited PDFs",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= FREE MODE =================
async def free_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    language = get_user_language(user_id)
    
    messages = {
        'english': "✅ Free Mode Activated!\n\n📝 **Now send me any text, and I'll convert it to PDF!**\n\nExample: Send me your notes or documents.",
        'amharic': "✅ ነፃ ሞድ ተጀምሯል!\n\n📝 **አሁን ማንኛውንም ጽሑፍ ይላኩልኝ፣ እኔ ወደ PDF አቀይረዋለሁ!**\n\nምሳሌ: ማስታወሻዎችዎን ወይም ሰነዶችዎን ይላኩልኝ።",
        'oromo': "✅ Modii bilisaa eegaleera!\n\n📝 **Amma barreeffama kamiyyuu naaf ergaa, ani gara PDFtti jijjiiru!**\n\nFakkeenyota: Barreeffamawwan kee yookiin dhaabbilee naaf ergi.",
        'tigrigna': "✅ ናጽ ሞድ ተጀሚሩ ኣሎ!\n\n📝 **ሕጂ ዝዀነ ይኹን ጽሑፍ ሰደዱለይ፣ ኣነ ናብ PDF ክቕይር እየ!**\n\nኣብነት: ኣስተውዕልታትካ ወይ ወስጣትካ ሰደዱለይ።"
    }
    
    if not can_use_free(user_id):
        limit_msg = {
            'english': "❌ Daily limit reached!\nYou used 3/3 free PDFs today.\nUse /start to upgrade.",
            'amharic': "❌ ዕለታዊ ገደብ ተደርሷል!\nዛሬ 3/3 ነፃ PDFዎችን ተጠቀሙ።\nለማሻሻል /start ይጠቀሙ።",
            'oromo': "❌ Daawwii guyyaa dhaqqabe!\nHar'aa PDF bilisaa 3/3 fayyadamte.\nFooyya'uuf /start fayyadami.",
            'tigrigna': "❌ ዕለታዊ ገደብ በጽሑ!\nሎሚ 3/3 ናጽ PDFታት ተጠቒምኩም።\nምልልስ ንምግባር /start ተጠቐሙ።"
        }
        await q.edit_message_text(limit_msg[language])
        return
    
    await q.edit_message_text(messages[language])

# ================= PREMIUM MODE =================
async def premium_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    language = get_user_language(user_id)
    
    if is_premium(user_id):
        messages = {
            'english': "✅ You are already Premium!\n\n📝 **Send me any text, and I'll convert it to PDF!**",
            'amharic': "✅ አስቀድመው ፕሪሚየም ነዎት!\n\n📝 **ማንኛውንም ጽሑፍ ይላኩልኝ፣ እኔ ወደ PDF አቀይረዋለሁ!**",
            'oromo': "✅ Duraanii Premium taatee jirta!\n\n📝 **Barreeffama kamiyyuu naaf ergaa, ani gara PDFtti jijjiiru!**",
            'tigrigna': "✅ ካብ ቅድሚ እዚ ፕሪሚየም ኢኻ!\n\n📝 **ዝዀነ ይኹን ጽሑፍ ሰደዱለይ፣ ኣነ ናብ PDF ክቕይር እየ!**"
        }
        await q.edit_message_text(messages[language])
        return
    
    messages = {
        'english': f"💎 PREMIUM ACCESS\n\nPrice: {PREMIUM_PRICE}\n📱 Telebirr: {TELEBIRR_NUMBER}\n🧾 Reference = {user_id}\n\n1. Send 30 Birr to Telebirr\n2. Use Reference above\n3. Take screenshot\n4. Click button below",
        'amharic': f"💎 ፕሪሚየም መዳረሻ\n\nዋጋ: {PREMIUM_PRICE}\n📱 ቴሌቢር: {TELEBIRR_NUMBER}\n🧾 ማጣቀሻ = {user_id}\n\n1. 30 ብር ለቴሌቢር ይላኩ\n2. ከፍተኛውን ማጣቀሻ ይጠቀሙ\n3. ስክሪንሾት ይፍጠሩ\n4. ከታች ያለውን አዝራር ይጫኑ",
        'oromo': f"💎 Dhaabbata Premium\n\nGatii: {PREMIUM_PRICE}\n📱 Telebirr: {TELEBIRR_NUMBER}\n🧾 Mallattoo = {user_id}\n\n1. Telebirr 30 Birrii ergaa\n2. Mallattoo ol fuudhu fayyadami\n3. Screenshot qabadhu\n4. Butoona gadi aanaa cuqsiisi",
        'tigrigna': f"💎 ፕሪሚየም መእተዊ\n\nዋጋ: {PREMIUM_PRICE}\n📱 ቴሌቢር: {TELEBIRR_NUMBER}\n🧾 መወከሲ = {user_id}\n\n1. 30 ብር ናብ ቴሌቢር ሰደዱ\n2. ኣብ ላዕሊ ዘሎ መወከሲ ተጠቐሙ\n3. ስክሪንሾት ግበሩ\n4. ኣብ ታሕቲ ዘሎ ኣዝራር ጠውቑ"
    }
    
    await q.edit_message_text(
        messages[language],
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📤 I Paid - Send Screenshot", callback_data="paid")]]
        )
    )

# ================= PAYMENT =================
async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    language = get_user_language(user_id)
    
    messages = {
        'english': "📸 **Please send your payment screenshot now.**",
        'amharic': "📸 **አሁን የክፍያ ስክሪንሾትዎን ይላኩ።**",
        'oromo': "📸 **Amma screenshot kaffaltii kee naaf ergi.**",
        'tigrigna': "📸 **ሕጂ ናይ ክፍሊት ስክሪንሾትኩም ሰደዱ።**"
    }
    
    await q.edit_message_text(messages[language])

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    file_id = update.message.photo[-1].file_id
    language = get_user_language(user_id)
    
    cur.execute(
        "INSERT INTO payments VALUES (?, ?, ?, ?)",
        (user_id, username, file_id, "pending")
    )
    db.commit()
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
        ]
    ]
    await context.bot.send_photo(
        ADMIN_ID,
        file_id,
        caption=f"💰 PAYMENT\nUser: @{username}\nID: {user_id}\nLanguage: {language}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    confirm_msg = {
        'english': "⏳ Waiting for admin approval...",
        'amharic': "⏳ የአስተዳዳሪ ማጽደቅ በመጠበቅ ላይ...",
        'oromo': "⏳ Murtii adminii eeggachaa jira...",
        'tigrigna': "⏳ ፍቓድ ኣስተዳደር ተጠቒሙ ኣሎ..."
    }
    
    await update.message.reply_text(confirm_msg[language])

# ================= ADMIN ACTION =================
async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action, user_id = q.data.split("_")
    user_id = int(user_id)
    language = get_user_language(user_id)
    
    if action == "approve":
        set_premium(user_id)
        
        messages = {
            'english': "✅ **Premium activated for 7 days!**\n\n📝 **Now send me any text, and I'll convert it to PDF!**",
            'amharic': "✅ **ፕሪሚየም ለ7 ቀናት ተግባራዊ ሆኗል!**\n\n📝 **አሁን ማንኛውንም ጽሑፍ ይላኩልኝ፣ እኔ ወደ PDF አቀይረዋለሁ!**",
            'oromo': "✅ **Premium guyyoota 7af eegaleera!**\n\n📝 **Amma barreeffama kamiyyuu naaf ergaa, ani gara PDFtti jijjiiru!**",
            'tigrigna': "✅ **ፕሪሚየም ን7 መዓልታት ተግባራዊ ኣቢሉ!**\n\n📝 **ሕጂ ዝዀነ ይኹን ጽሑፍ ሰደዱለይ፣ ኣነ ናብ PDF ክቕይር እየ!**"
        }
        
        await context.bot.send_message(user_id, messages[language])
        await q.edit_message_caption(f"✅ Approved user {user_id}")
    else:
        reject_msg = {
            'english': "❌ Payment rejected by admin.",
            'amharic': "❌ ክፍያ በአስተዳዳሪ ተቀባይነት አላገኘም።",
            'oromo': "❌ Kaffaltiin adminiin dhiifame.",
            'tigrigna': "❌ ክፍሊት ብኣስተዳደር ተነጺጉ።"
        }
        
        await context.bot.send_message(user_id, reject_msg[language])
        await q.edit_message_caption(f"❌ Rejected user {user_id}")

# ================= TEXT TO PDF =================
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    language = get_user_language(user_id)
    
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    db.commit()
    
    cur.execute("SELECT captcha_passed FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row or row[0] == 0:
        await update.message.reply_text("❌ Please do /start first")
        return
    
    # Check channel membership
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status not in ["member", "creator", "administrator"]:
            await update.message.reply_text(
                f"❌ You must join {CHANNEL_USERNAME} first!\nUse /start"
            )
            return
    except:
        await update.message.reply_text(
            f"❌ You must join {CHANNEL_USERNAME} first!\nUse /start"
        )
        return
    
    if is_premium(user_id):
        await create_pdf(update, user_text, True, language)
        return
    
    if not can_use_free(user_id):
        limit_msg = {
            'english': "❌ Daily limit reached! You used 3/3 free PDFs today.",
            'amharic': "❌ ዕለታዊ ገደብ ተደርሷል! ዛሬ 3/3 ነፃ PDFዎችን ተጠቀሙ።",
            'oromo': "❌ Daawwii guyyaa dhaqqabe! Har'aa PDF bilisaa 3/3 fayyadamte.",
            'tigrigna': "❌ ዕለታዊ ገደብ በጽሑ! ሎሚ 3/3 ናጽ PDFታት ተጠቒምኩም።"
        }
        await update.message.reply_text(limit_msg[language])
        return
    
    increment_free_usage(user_id)
    await create_pdf(update, user_text, False, language)

async def create_pdf(update: Update, text_content: str, premium: bool, language: str):
    user_id = update.effective_user.id
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"PDF_{user_id}_{timestamp}.pdf"
    
    c = canvas.Canvas(file_name, pagesize=A4)
    
    # NO TITLE - Start writing user's text immediately
    c.setFont("Helvetica", 12)
    
    # Split text into lines
    lines = text_content.split('\n')
    
    # Start from top
    y_position = 800  # Top of page
    
    for line in lines:
        # Check if we need new page
        if y_position < 50:
            c.showPage()
            c.setFont("Helvetica", 12)
            y_position = 800  # Back to top
        
        # Write the line
        c.drawString(50, y_position, line)
        y_position -= 20  # Move down
    
    c.save()
    
    # Send PDF
    await update.message.reply_document(
        document=open(file_name, "rb"),
        filename=f"Document_{timestamp}.pdf",
        caption="✅ PDF Generated!"
    )

# ================= WEB SERVER FOR UPTIMEROBOT =================
print("🚀 Setting up web server for 24/7 uptime...")

try:
    from flask import Flask
    import threading
    
    flask_app = Flask(__name__)
    
    @flask_app.route('/')
    def home():
        return """
        <html>
            <head><title>Text to PDF Bot</title></head>
            <body style="text-align: center; padding: 50px; font-family: Arial;">
                <h1>🤖 Text to PDF Bot</h1>
                <p>✅ Bot is running 24/7!</p>
                <p>Telegram: <a href="https://t.me/texttopdff_bot">@texttopdff_bot</a></p>
                <p>Status: <span style="color: green;">● ONLINE</span></p>
            </body>
        </html>
        """
    
    @flask_app.route('/ping')
    def ping():
        return "pong"
    
    def run_web():
        flask_app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
    
    # Start web server
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    print("✅ Web server started on port 8080")
    print(f"🌐 URL for UptimeRobot: https://pdf-converter--eldu8289.replit.app")
    
except Exception as e:
    print(f"⚠️ Web server error: {e}")

# ================= MAIN =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(captcha_check, pattern="cap_"))
app.add_handler(CallbackQueryHandler(check_join_callback, pattern="check_join"))
app.add_handler(CallbackQueryHandler(language_selection, pattern="lang_"))
app.add_handler(CallbackQueryHandler(free_choice, pattern="free_choice"))
app.add_handler(CallbackQueryHandler(premium_choice, pattern="premium_choice"))
app.add_handler(CallbackQueryHandler(paid, pattern="paid"))
app.add_handler(CallbackQueryHandler(admin_action, pattern="approve_|reject_"))
app.add_handler(MessageHandler(filters.PHOTO, receive_screenshot))

# Text handler
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

print("=" * 50)
print("🤖 BOT STARTING...")
print(f"📱 Telegram: @texttopdff_bot")
print(f"🔑 Token: {BOT_TOKEN[:10]}...")
print(f"👤 Admin: {ADMIN_ID}")
print("=" * 50)

app.run_polling()