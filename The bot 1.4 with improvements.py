import instaloader
import logging
import os
import time
from pyrogram import Client, filters, enums
from pyrogram.types import Message, BotCommand
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from cryptography.fernet import Fernet
import asyncio

# Load environment variables from .env file
load_dotenv()

# Logging configuration with levels
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# API credentials from environment variables
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Encryption key for secure password storage
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY").encode()
cipher_suite = Fernet(ENCRYPTION_KEY)

# Initialize the Pyrogram Client
app = Client("instagram_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# In-memory storage for user tasks
running_tasks = {}

# Granular logging setup
user_logs = {}

def log_user_activity(user_id, action):
    if user_id not in user_logs:
        user_logs[user_id] = []
    user_logs[user_id].append(f"{action} at {time.strftime('%Y-%m-%d %H:%M:%S')}")

def encrypt_password(password):
    return cipher_suite.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password):
    return cipher_suite.decrypt(encrypted_password.encode()).decode()

def get_non_followers(username, encrypted_password):
    L = instaloader.Instaloader()
    password = decrypt_password(encrypted_password)

    try:
        if len(password) < 6:
            raise instaloader.exceptions.BadCredentialsException("Invalid password length.")

        L.login(username, password)
        logging.info(f"Login successful for user {username}.")
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        return None, "Two-factor authentication is enabled on your account. Please disable 2FA and try again."
    except instaloader.exceptions.BadCredentialsException:
        return None, "Invalid username or password. Please try again."
    except instaloader.exceptions.ConnectionException:
        return None, "Connection error. Please check your network."
    except Exception as e:
        return None, f"An unexpected error occurred: {e}"

    try:
        profile = instaloader.Profile.from_username(L.context, username)
        logging.info(f"Profile loaded: {profile.username}")
    except Exception as e:
        return None, f"Error loading profile: {e}"

    followers = set(follower.username for follower in profile.get_followers())
    followees = set(followee.username for followee in profile.get_followees())
    non_followers = followees - followers

    return non_followers, None

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply(
        "Welcome to the Instagram Non-Follower Checker Bot! 🤖\n\n"
        "To get started, send your Instagram username and password separated by a space.\n"
        "Commands available:\n"
        "/help - List of commands\n"
        "/stop - Stop the current operation\n"
        "/schedule - Schedule regular checks (future update)\n\n"
       "**Note**: If you have two-factor authentication (2FA) enabled, please disable it before using this bot." 
    )
    log_user_activity(message.from_user.id, "/start command issued")

@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    help_text = """
    **Available Commands:**
    /start - Start the bot and see instructions
    /stop - Stop the current operation
    /help - Display this help message
    /schedule - Schedule regular checks (coming soon)
    
    **Usage:**
    Send your Instagram credentials as `username password` to check for non-followers.
    
    **Note:**
    If you have two-factor authentication (2FA) enabled, please disable it before using this bot.
    """
    await message.reply(help_text)
    log_user_activity(message.from_user.id, "/help command issued")

@app.on_message(filters.command("stop"))
async def stop(client, message: Message):
    user_id = message.from_user.id
    if user_id in running_tasks:
        running_tasks[user_id] = False
        await message.reply("The operation has been stopped.")
    else:
        await message.reply("No ongoing task found to stop.")
    log_user_activity(user_id, "/stop command issued")

@app.on_message(filters.text)
async def check_non_followers(client, message: Message):
    user_id = message.from_user.id
    try:
        username, password = message.text.split(" ", 1)
    except ValueError:
        await message.reply("Please provide both your username and password separated by a space.")
        return

    encrypted_password = encrypt_password(password)
    running_tasks[user_id] = True
    await client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    await message.reply("Checking non-followers... This may take a while.")

    # Run the check in a separate thread
    loop = asyncio.get_event_loop()
    non_followers, error = await loop.run_in_executor(None, get_non_followers, username, encrypted_password)

    if error:
        await message.reply(f"Error: {error}")
    elif non_followers:
        await save_and_send_non_followers(client, message, non_followers)
    else:
        await message.reply("Everyone follows you back!")

    running_tasks.pop(user_id, None)
    log_user_activity(user_id, "Non-follower check completed")

async def save_and_send_non_followers(client, message, non_followers):
    if non_followers:
        response = "These people don't follow you back:\n" + "\n".join(non_followers)
        if len(response) > 4096:  # Telegram message limit
            file_path = f"non_followers_{message.from_user.id}.txt"
            with open(file_path, 'w') as f:
                f.write(response)
            await client.send_document(message.chat.id, file_path, caption="List of people who don't follow you back.")
            os.remove(file_path)
        else:
            await client.send_message(message.chat.id, response)
    else:
        await client.send_message(message.chat.id, "Everyone follows you back!")

@app.on_message(filters.command("schedule"))
async def schedule_check(client, message: Message):
    await message.reply("Scheduled checks are not implemented yet, but stay tuned for updates!")
    log_user_activity(message.from_user.id, "/schedule command issued")

# Adding command menu using BotCommand
commands = [
    BotCommand("start", "Start the bot and see instructions"),
    BotCommand("help", "Get a list of commands and usage instructions"),
    BotCommand("stop", "Stop any ongoing operation"),
    BotCommand("schedule", "Schedule regular non-follower checks")
]

async def set_commands():
    await app.set_bot_commands(commands)

if __name__ == "__main__":
    app.run()

