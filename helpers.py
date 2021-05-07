
import random
import requests
import os
import json
import datetime
from bson.objectid import ObjectId
from urllib.parse import urlencode

from telegram import (
    Update,
    Bot,
    User,
    constants
)

from mongo import (
    Chats,
    # Schedules,
    # Rosters,
    # Duties,
    Users
)

from logger import logger

user_properties = [
    'id',
    'first_name',
    'last_name',
    'username',
    'is_bot',
    'language_code',
]

chat_properties = [
    'id',
    'type',
    'title',
    'all_members_are_administrators',
]

VAMONKE_ID = 265435469

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN') or '1783406286:AAElzXepih8u3OwKtvlvLYy3GC2eL8r1Ejk'
TEST_TELEGRAM_TOKEN = '1798724954:AAGuKOTuVWX8qfuRLUx1EU82Di9czAR6kFs'

ENVIRONMENT = os.environ.get('ENVIRONMENT')
IS_DEV = ENVIRONMENT is not 'prod'

def get_name_from_user_id(user_id):
    user_dict = Users.find_one({ 'id': user_id })
    if user_dict is None:
        return "❓"
    user = User(**user_dict)
    return user.mention_markdown_v2()

def get_user_dict_from_user(user):
    user_dict = { k: v for k, v in user.__dict__.items() if k in user_properties }
    return user_dict

def get_chat_dict_from_chat(chat):
    chat_dict = { k: v for k, v in chat.__dict__.items() if k in chat_properties }
    return chat_dict

def get_whitelisted_chats():
    chats = Chats.find({ 'isWhitelisted': True })
    chat_ids = [c['id'] for c in list(chats)]
    return chat_ids

def get_whitelisted_users():
    users = Users.find({ 'isWhitelisted': True })
    user_ids = [u['id'] for u in list(users)]
    return user_ids

def get_is_whitelisted(update):
    user_id = update.effective_user.id
    user_dict = Users.find_one({ 'id': user_id })
    if user_dict and user_dict.get('isWhitelisted'):
        return True

    chat_id = update.effective_chat.id
    chat_dict = Chats.find_one({ 'id': chat_id })
    if chat_dict and chat_dict.get('isWhitelisted'):
        return True

    return False

def configure_telegram():
    """
    Configures the bot with a Telegram Token.
    Returns a bot instance.
    """
    TOKEN = TEST_TELEGRAM_TOKEN if IS_DEV else TELEGRAM_TOKEN
    if not TOKEN:
        logger.error('The TELEGRAM_TOKEN must be set')
        raise NotImplementedError

    # print(TOKEN)
    return Bot(TOKEN)

def alert_creator(message):
    bot = configure_telegram()
    bot.send_message(
        chat_id=VAMONKE_ID,
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )