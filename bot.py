import os
import sqlite3
import telebot
from telebot import types

# Securely fetch token and admin id from Environment Variables (Render/Koyeb)
TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6913254882"))

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- SQLite Database Setup ---
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT
        )
    ''')
    # Channels table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            user_id INTEGER,
            channel TEXT,
            PRIMARY KEY (user_id, channel)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Database Helper Functions
def add_user_db(user_id, name, username):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, name, username) VALUES (?, ?, ?)', (user_id, name, username))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, name, username FROM users')
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_channel_db(user_id, channel):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO channels (user_id, channel) VALUES (?, ?)', (user_id, channel))
    conn.commit()
    conn.close()

def get_user_channels(user_id):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT channel FROM channels WHERE user_id = ?', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_all_channels():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT channel FROM channels')
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

# Caches for workflow
post_cache = {}
broadcast_target = {}
help_mode = set()
broadcast_mode = set()

# Main Persistent Keyboard
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("✨ Create Post"),
        types.KeyboardButton("📢 Add Channel")
    )
    markup.add(
        types.KeyboardButton("📁 My Channels"),
        types.KeyboardButton("🛟 Help & Support")
    )
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("👑 Admin Panel"))
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    name = message.from_user.first_name
    username = message.from_user.username or "None"

    # Check if user already exists in DB
    existing_users = [u[0] for u in get_all_users()]
    if user_id not in existing_users:
        if user_id != ADMIN_ID:
            try:
                bot.send_message(
                    ADMIN_ID,
                    f"🚨 **New User Alert!**\n\n"
                    f"👤 Name: {name}\n"
                    f"🆔 ID: <code>{user_id}</code>\n"
                    f"🔗 Username: @{username}"
                )
            except Exception:
                pass

    add_user_db(user_id, name, username)

    welcome_text = (
        f"👋 **Welcome {name} to Controller Bot!**\n\n"
        "I can help you manage your Telegram channels and groups professionally with rich posts, inline buttons, and multi-channel publishing.\n\n"
        "👇 **Select an option from the menu keyboard below:**"
    )
    bot.send_message(user_id, welcome_text, reply_markup=get_main_keyboard(user_id))

# Reply Keyboard Handlers
@bot.message_handler(func=lambda msg: msg.text in [
    "✨ Create Post", "📢 Add Channel", "📁 My Channels", "🛟 Help & Support", "👑 Admin Panel"
])
def handle_menu_buttons(message):
    user_id = message.from_user.id
    text = message.text

    if text == "📢 Add Channel":
        bot.send_message(
            user_id, 
            "➕ **How to add a channel/group:**\n\n"
            "1. Add this bot to your channel/group as an **Administrator** with post permissions.\n"
            "2. Send your channel username or ID here (e.g., `@mychannel` or `-100123456789`)."
        )
        bot.register_next_step_handler(message, save_user_channel)

    elif text == "📁 My Channels":
        channels = get_user_channels(user_id)
        if not channels:
            bot.send_message(user_id, "❌ Apni ekhono kono channel ba group add korenni. Prothome '📢 Add Channel' use korun.")
        else:
            ch_list = "\n".join([f"• <code>{ch}</code>" for ch in channels])
            bot.send_message(user_id, f"📁 **Apnar Connected Channels/Groups:**\n\n{ch_list}")

    elif text == "✨ Create Post":
        channels = get_user_channels(user_id)
        if not channels:
            bot.send_message(user_id, "⚠️ Prothome '📢 Add Channel' diye ekta channel/group add korun.")
            return

        markup = types.InlineKeyboardMarkup()
        for ch in channels:
            markup.add(types.InlineKeyboardButton(ch, callback_data=f"sel_ch_{ch}"))
        
        bot.send_message(user_id, "🎯 **Select target channel/group for posting:**", reply_markup=markup)

    elif text == "🛟 Help & Support":
        help_mode.add(user_id)
        bot.send_message(user_id, "🛟 **Help Desk:**\n\nApnar jekono somossa ba question ekhane likhe pathan. Seta direct admin-er kache chole jabe!")

    elif text == "👑 Admin Panel" and user_id == ADMIN_ID:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
            types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_menu"),
            types.InlineKeyboardButton("👥 User List", callback_data="admin_users"),
            types.InlineKeyboardButton("📁 Channel List", callback_data="admin_channels")
        )
        bot.send_message(user_id, "👑 **Admin Control Panel:**", reply_markup=markup)

def save_user_channel(message):
    user_id = message.from_user.id
    channel = message.text.strip()
    if not channel.startswith("@") and not channel.startswith("-"):
        bot.send_message(user_id, "❌ Invalid format! Please use `@channelusername` or valid chat ID starting with `-100`.")
        return

    add_channel_db(user_id, channel)
    bot.send_message(user_id, f"✅ Channel/Group <b>{channel}</b> successfully added!")

# User Help Message Handler
@bot.message_handler(func=lambda msg: msg.from_user.id in help_mode)
def process_help_message(message):
    user_id = message.from_user.id
    help_mode.remove(user_id)
    
    users = get_all_users()
    user_name = str(user_id)
    for u in users:
        if u[0] == user_id:
            user_name = f"{u[1]} (@{u[2]})"
            break
    
    try:
        bot.send_message(
            ADMIN_ID,
            f"📩 **New Help Request!**\n\n"
            f"👤 From: {user_name}\n"
            f"🆔 ID: <code>{user_id}</code>\n\n"
            f"💬 Message:\n{message.text}"
        )
        bot.send_message(user_id, "✅ Apnar message admin-er kache successfully pathano hoyeche!")
    except Exception as e:
        bot.send_message(user_id, f"❌ Failed to send message. Error: {e}")

# Inline Callbacks Handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data

    if data.startswith("sel_ch_"):
        ch_name = data.replace("sel_ch_", "")
        post_cache[user_id] = {"target": ch_name, "text": "", "photo": None, "buttons": []}
        bot.answer_callback_query(call.id)
        bot.send_message(user_id, f"✅ Target set to: <b>{ch_name}</b>\n\nEkhon apnar post-er **Text** ba **Photo with caption** send korun:")
        bot.register_next_step_handler(call.message, receive_post_content)

    elif data == "add_url_button":
        bot.answer_callback_query(call.id)
        bot.send_message(user_id, "🔗 Send button details in this format:\n<code>Button Text - https://example.com</code>")
        bot.register_next_step_handler(call.message, receive_url_button)

    elif data == "publish_post":
        bot.answer_callback_query(call.id)
        post_data = post_cache.get(user_id)
        if not post_data:
            bot.send_message(user_id, "❌ No post data found.")
            return

        target = post_data["target"]
        text = post_data["text"]
        photo = post_data["photo"]
        buttons = post_data["buttons"]

        markup = types.InlineKeyboardMarkup()
        for btn in buttons:
            markup.add(types.InlineKeyboardButton(btn['text'], url=btn['url']))

        try:
            if photo:
                bot.send_photo(target, photo, caption=text, reply_markup=markup if buttons else None)
            else:
                bot.send_message(target, text, reply_markup=markup if buttons else None)
            
            bot.send_message(user_id, f"🎉 **Successfully posted to {target}!**")
        except Exception as e:
            bot.send_message(user_id, f"❌ Failed to post. Make sure bot is Admin in <b>{target}</b>.\nError: <code>{e}</code>")

    # Admin Panel Actions
    elif user_id == ADMIN_ID:
        if data == "admin_stats":
            users = get_all_users()
            channels = get_all_channels()
            bot.answer_callback_query(call.id)
            bot.send_message(ADMIN_ID, f"📊 **Bot Statistics (Database):**\n\n👥 Total Users: {len(users)}\n📁 Total Connected Channels/Groups: {len(channels)}")

        elif data == "admin_users":
            bot.answer_callback_query(call.id)
            users = get_all_users()
            if not users:
                bot.send_message(ADMIN_ID, "❌ Kono user nei.")
            else:
                u_list = "\n".join([f"• {u[1]} (@{u[2]}) - ID: <code>{u[0]}</code>" for u in users[:40]])
                bot.send_message(ADMIN_ID, f"👥 **Users List (Max 40):**\n\n{u_list}")

        elif data == "admin_channels":
            bot.answer_callback_query(call.id)
            channels = get_all_channels()
            if not channels:
                bot.send_message(ADMIN_ID, "❌ Kono channel add kora hoyni.")
            else:
                c_list = "\n".join([f"• <code>{ch}</code>" for ch in channels[:40]])
                bot.send_message(ADMIN_ID, f"📁 **Channels/Groups List (Max 40):**\n\n{c_list}")

        elif data == "admin_broadcast_menu":
            bot.answer_callback_query(call.id)
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("📢 All Users", callback_data="bc_users"),
                types.InlineKeyboardButton("📢 All Channels", callback_data="bc_channels"),
                types.InlineKeyboardButton("📢 Both (Users + Channels)", callback_data="bc_both")
            )
            bot.send_message(ADMIN_ID, "📢 **Select Broadcast Target:**", reply_markup=markup)

        elif data.startswith("bc_"):
            bot.answer_callback_query(call.id)
            target_type = data.replace("bc_", "")
            broadcast_target[ADMIN_ID] = target_type
            broadcast_mode.add(ADMIN_ID)
            bot.send_message(ADMIN_ID, f"📢 **Broadcast Mode ({target_type}):**\n\nEkhon message ba photo send korun ja targetder kache chole jabe.")

def receive_post_content(message):
    user_id = message.from_user.id
    if user_id not in post_cache:
        return

    if message.photo:
        post_cache[user_id]["photo"] = message.photo[-1].file_id
        post_cache[user_id]["text"] = message.caption or ""
    else:
        post_cache[user_id]["text"] = message.text or ""

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add URL Button", callback_data="add_url_button"),
        types.InlineKeyboardButton("🚀 Publish Now", callback_data="publish_post")
    )
    bot.send_message(user_id, "✨ **Post content saved!** Choose next action:", reply_markup=markup)

def receive_url_button(message):
    user_id = message.from_user.id
    if user_id not in post_cache:
        return

    try:
        parts = message.text.split("-")
        btn_text = parts[0].strip()
        btn_url = parts[1].strip()
        post_cache[user_id]["buttons"].append({"text": btn_text, "url": btn_url})
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Add Another Button", callback_data="add_url_button"),
            types.InlineKeyboardButton("🚀 Publish Now", callback_data="publish_post")
        )
        bot.send_message(user_id, f"✅ Button <b>{btn_text}</b> added successfully!", reply_markup=markup)
    except Exception:
        bot.send_message(user_id, "❌ Wrong format! Send like:\n<code>Click Here - https://t.me/...</code>")

# Admin Broadcast Executor
@bot.message_handler(func=lambda msg: msg.from_user.id in broadcast_mode and msg.from_user.id == ADMIN_ID)
def execute_broadcast(message):
    admin_id = message.from_user.id
    broadcast_mode.remove(admin_id)
    target = broadcast_target.get(admin_id, "both")

    success_count = 0
    targets_list = []

    if target in ["users", "both"]:
        users = get_all_users()
        targets_list.extend([u[0] for u in users])
    if target in ["channels", "both"]:
        channels = get_all_channels()
        targets_list.extend(channels)

    for t in targets_list:
        try:
            if message.photo:
                bot.send_photo(t, message.photo[-1].file_id, caption=message.caption or "")
            else:
                bot.send_message(t, message.text)
            success_count += 1
        except Exception:
            pass

    bot.send_message(admin_id, f"📢 **Broadcast Completed!** Successfully sent to {success_count} targets ({target}).")

if __name__ == "__main__":
    print("Bot with SQLite Database is active and running smoothly...")
    bot.infinity_polling()
