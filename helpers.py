import random
import requests
import os
import pymongo
import datetime
# from bson.objectid import ObjectId
from urllib.parse import urlencode

from telegram import (
    Update,
    Bot,
    User,
    Message,
    InlineKeyboardButton,
    constants
)

from mongo import (
    Chats,
    # Schedules,
    Rosters,
    Duties,
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

week_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
week_days_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# TELEGRAM_TOKEN = '1783406286:AAElzXepih8u3OwKtvlvLYy3GC2eL8r1Ejk'
# TELEGRAM_TOKEN = '1798724954:AAEadvyQikDry8r1Qy0CyPDL__iRLRi0at8'
# TEST_TELEGRAM_TOKEN = '1798724954:AAEadvyQikDry8r1Qy0CyPDL__iRLRi0at8'

GIPHY_API_KEY = '1iI19SCF571Lt9CV2uNsXv3t1CzIRznM'

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
    return True
    # user_id = update.effective_user.id
    # user_dict = Users.find_one({ 'id': user_id })
    # if user_dict and user_dict.get('isWhitelisted'):
    #     return True

    # chat_id = update.effective_chat.id
    # chat_dict = Chats.find_one({ 'id': chat_id })
    # if chat_dict and chat_dict.get('isWhitelisted'):
    #     return True

    # return False

def configure_telegram():
    """
    Configures the bot with a Telegram Token.
    Returns a bot instance.
    """
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    if not TELEGRAM_TOKEN:
        logger.error('The TELEGRAM_TOKEN must be set')
        raise NotImplementedError

    # print(TELEGRAM_TOKEN)
    return Bot(TELEGRAM_TOKEN)

def alert_creator(message):
    bot = configure_telegram()
    bot.send_message(
        chat_id=VAMONKE_ID,
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def add_user_to_roster(user_dict, roster_id):
    return Rosters.find_one_and_update(
        { '_id': roster_id },
        { '$addToSet':
            { "schedule": user_dict },
        },
        return_document=pymongo.ReturnDocument.AFTER,
    )

def send_gif(message: Message):
    url = get_gif()
    message.reply_animation(animation=url, quote=False)

def get_gif():
    random.seed()
    offset = random.randint(0, 100)
    search_url = 'https://api.giphy.com/v1/gifs/search'
    params = urlencode({
        'api_key': GIPHY_API_KEY,
        'q': 'well done',
        'limit': 1,
        'offset': offset,
    })
    contents = requests.get(search_url + '?' + params).json()
    url = contents['data'][0]['images']['fixed_height']['url']
    return url

def duty_to_button(duty, callback_text):
    button_text = duty['name'] + duty['date'].strftime(" %a %d %b")
    roster_id = duty['_id']
    callback_data = fr'{callback_text}.{roster_id}'
    # print(button_text + ' ' + callback_data)
    return [InlineKeyboardButton(button_text, callback_data=callback_data)]

def find_incomplete_duties(chat_id: int, user_id: int, from_date, to_date):
    # TODO: Aggregate and use $lookup to populate roster names

    # Get duties in date window
    logger.info(f'Fetching incomplete duties with chat_id {chat_id} user_id {user_id} between {from_date} and {to_date}')
    incomplete_duties = Duties.find({
        'chat_id': chat_id,
        'user': user_id,
        'isCompleted': False,
        'date': { '$gte': from_date, '$lte': to_date }
    }, sort=[('date', 1)])

    incomplete_duties = list(incomplete_duties)
    logger.info(fr'Found incomplete duties {incomplete_duties}')
    
    return incomplete_duties

def send_chore_missing_message(update: Update):
    query = update.callback_query
    message = 'Oops! This chore has been removed.'
    logger.info('Edit message:\n' + message)
    query.edit_message_text(text=message)

cancel_button = [InlineKeyboardButton("✖ Cancel", callback_data=fr'cancel')]

def add_name_to_duty(duty: dict) -> dict:
    logger.info(fr'Add roster name to duty {duty["roster_id"]}')
    roster = Rosters.find_one(duty['roster_id'])
    duty['name'] = roster['name']
    return duty

def date_to_button(date: datetime.datetime, callback_text: str):
    button_text = date.strftime("%a %d %b")
    date_str = date.strftime("%x")
    callback_data = fr'{callback_text}.{date_str}'
    print(callback_data)
    return [InlineKeyboardButton(button_text, callback_data=callback_data)]

def is_duty_weekly(duty: dict, roster: dict):
    roster_schedule = roster['schedule']
    user_id = duty['user']
    duty_date = duty['date']
    duty_day = duty_date.weekday()

    is_weekly_duty = any(
        (us['dutyDay'] == duty_day and us['id'] == user_id)
        for us in roster_schedule
    )
    return is_weekly_duty

def create_chat(update):
    # Get user
    user = update.effective_user
    user_id = user.id

    # Get chat
    chat = update.effective_chat
    chat_dict = get_chat_dict_from_chat(chat)
    chat_dict['addedBy'] = user_id
    chat_dict['createdAt'] = datetime.datetime.now()

    # Add chat
    Chats.update_one(
        { 'id': chat_dict['id'] },
        { '$set': chat_dict },
        upsert=True
    )