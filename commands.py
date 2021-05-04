import random
import pymongo
import requests
import logging
import os
import json
import datetime
from urllib.parse import urlencode

from telegram import Update, ForceReply, Bot, User, InlineKeyboardMarkup, InlineKeyboardButton, constants
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CommandHandler, CallbackQueryHandler, CallbackContext

week_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
week_days_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# MONGODB_URI = 'mongodb+srv://vamonke:bDlccB4w6Ads4jmk@housechores.cerl9.mongodb.net/housechores?retryWrites=true&w=majority'
# TEST_MONGODB_URI = 'mongodb://localhost:27017/'
TEST_MONGODB_URI = 'mongodb+srv://vamonke:bDlccB4w6Ads4jmk@housechores.cerl9.mongodb.net/housechores?retryWrites=true&w=majority'

GIPHY_API_KEY = '1iI19SCF571Lt9CV2uNsXv3t1CzIRznM'

logger = logging.getLogger()
if logger.handlers:
    for handler in logger.handlers:
        logger.removeHandler(handler)
logging.basicConfig(level=logging.INFO)

user_properties = [
    'id',
    'first_name',
    'last_name',
    'username',
    'is_bot',
    'language_code',
]

def setup_mongodb():
    """
    Setup mongodb client with mongodb uri.
    Returns a mongodb database instance.
    """

    MONGODB_URI = os.environ.get('MONGODB_URI')
    # MONGODB_URI = TEST_MONGODB_URI
    if not MONGODB_URI:
        logger.error('The MONGODB_URI must be set')
        raise NotImplementedError

    mongo_client = pymongo.MongoClient(MONGODB_URI)
    database_name = "housechores"
    mongo_db = mongo_client[database_name]
    return mongo_db

def get_name_from_user_id(users, user_id):
    user_dict = users.find_one({ 'id': user_id })
    if user_dict is None:
        return "❓"
    user = User(**user_dict)
    return user.mention_markdown_v2()

def start(update: Update) -> str:
    """Return a message when the command /start is issued."""
    user = update.effective_user
    return fr'Hi {user.mention_markdown_v2()}\!'

def join(update: Update) -> str:
    """Send a message when the command /join is issued."""
    user = update.effective_user
    user_dict = { k: v for k, v in user.__dict__.items() if k in user_properties }
    user_dict['isRemoved'] = False
    user_dict['createdAt'] = datetime.datetime.now()

    users = setup_mongodb()["users"]

    result = users.find_one_and_update(
        { 'id': user_dict['id'] },
        { '$setOnInsert': user_dict },
        upsert=True,
    )
    message = fr'👋 Hi {user.mention_markdown_v2()}\! Which day do you want to do your duty\?'

    keyboard = [
        [InlineKeyboardButton("Monday", callback_data='join.0')],
        [InlineKeyboardButton("Tuesday", callback_data='join.1')],
        [InlineKeyboardButton("Wednesday", callback_data='join.2')],
        [InlineKeyboardButton("Thursday", callback_data='join.3')],
        [InlineKeyboardButton("Friday", callback_data='join.4')],
        [InlineKeyboardButton("Saturday", callback_data='join.5')],
        [InlineKeyboardButton("Sunday", callback_data='join.6')],
        [InlineKeyboardButton("Any day", callback_data='join.Any')],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    return (message, reply_markup)

def leave(update: Update) -> str:
    """Send a message when the command /leave is issued."""
    user = update.effective_user
    user_dict = { k: v for k, v in user.__dict__.items() if k in user_properties }
    user_dict['isRemoved'] = True
    user_dict['modifiedAt'] = datetime.datetime.now()

    users = setup_mongodb()["users"]
    result = users.find_one_and_update(
        { 'id': user_dict['id'] },
        { '$set': user_dict },
        upsert=True,
    )

    if result is None or result['isRemoved']:
        return fr'{user.mention_markdown_v2()} is already not in the duty roster'

    return fr'{user.mention_markdown_v2()} left'

def callback_handler(update: Update) -> str:
    query = update.callback_query
    query.answer()

    [callback_type, query_data] = query.data.split('.')

    if callback_type == 'join':
        join_callback(update, query_data)
    elif callback_type == 'reschedule':
        reschedule_callback(update, query_data)

    return (None, None)

def join_callback(update, query_data):
    query = update.callback_query
    user = update.effective_user

    if query_data == 'Any':
        message = f"{user.mention_markdown_v2()} has chosen to do their duty on *any day* 👌"
        query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)
        return None

    duty_day = int(query_data)
    day = week_days[duty_day]

    mongo_db = setup_mongodb()
    users = mongo_db["users"]
    user_dict = users.find_one_and_update(
        { 'id': user.id },
        { '$set':
            {
                'isRemoved': False,
                'dutyDay': duty_day,
                'modifiedAt': datetime.datetime.now()
            }
        },
        upsert=True,
        return_document=pymongo.ReturnDocument.AFTER,
    )

    message = f"{user.mention_markdown_v2()} has chosen to do their duty on *{day}* 👌"
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)

    create_user_duties(mongo_db, user_dict, update)

def create_user_duties(mongo_db, user_dict, update):
    """Create duties for a user"""

    # print('user_dict', user_dict)
    if user_dict is None or user_dict['isRemoved'] or 'dutyDay' not in user_dict:
        return

    # Get window to create duties
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    start_of_cycle = today - datetime.timedelta(days=today.weekday())
    end_of_cycle = start_of_cycle + datetime.timedelta(weeks=2)

    # Get mongodb inserts
    requests = []
    day = user_dict['dutyDay']
    date = start_of_cycle + datetime.timedelta(days=day)
    while (date < end_of_cycle):
        if (date < today):
            date += datetime.timedelta(weeks=1)
            continue
        duty = {
            'user': user_dict['id'],
            'date': date,
            'createdAt': now,
            'isCompleted': False,
        }
        # logger.info('duty', duty)
        request = pymongo.UpdateOne(duty, { '$setOnInsert': duty }, upsert=True)
        requests.append(request)
        date += datetime.timedelta(weeks=1)

    # Run mongodb inserts
    duties = mongo_db["duties"]
    result = duties.bulk_write(requests)
    logger.info('result', result.bulk_api_result)

    user_next_duty(mongo_db, user_dict, update)

def create_duties() -> str:
    """Create duties when the command /createduties is issued."""
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    start_of_cycle = today - datetime.timedelta(days=today.weekday())
    end_of_cycle = start_of_cycle + datetime.timedelta(weeks=2)

    requests = []

    mongo_db = setup_mongodb()
    users = setup_mongodb()["users"]
    cursor = users.find({ 'isRemoved': False }).sort('dutyDay')

    for user_dict in cursor:
        if 'dutyDay' in user_dict:
            day = user_dict['dutyDay']
            date = start_of_cycle + datetime.timedelta(days=day)
            while (date < end_of_cycle):
                if (date < today):
                    date += datetime.timedelta(weeks=1)
                    continue
                duty = {
                    'user': user_dict['id'],
                    'date': date,
                    'createdAt': now,
                    'isCompleted': False,
                }
                request = pymongo.UpdateOne(
                    duty,
                    { '$setOnInsert': duty },
                    upsert=True
                )
                requests.append(request)
                date += datetime.timedelta(weeks=1)

    duties = mongo_db["duties"]

    # print(requests)
    result = duties.bulk_write(requests)
    logger.info('result', result.bulk_api_result)
    
    # end_of_cycle_date = end_of_cycle.strftime("%-d %b %Y")
    # message = f"{result.matched_count + result.upserted_count} duties created til {end_of_cycle_date}" # TODO: Fix count

    # return message

def show_schedule(update: Update) -> str:
    """Send a message when the command /showschedule is issued."""

    message = ""

    mongo_db = setup_mongodb()
    schedules = mongo_db["schedules"]
    users = setup_mongodb()["users"]

    schedule = schedules.find_one()

    if schedule is None:
        message += fr"No schedule found" + "\n\n"
    else:
        schedule_name = schedule['name']
        message += fr"*{schedule_name}*" + "\n\n"

    days = ['' for _ in range(7)]
    anyday = None

    cursor = users.find({ 'isRemoved': False }).sort('dutyDay')
    for user_dict in cursor:
        user = User(**user_dict)
        user_text = user.mention_markdown_v2()

        if 'dutyDay' in user_dict:
            day = int(user_dict['dutyDay'])
            days[day] = user_text
        else:
            anyday = user_text

    for index, person in enumerate(days):
        message += fr"`{week_days_short[index]}`\: {person}" + "\n"

    if anyday is not None:
        message += "\n" + fr"`Any`\: {anyday}"

    return message

def reschedule(update: Update):
    """Reschedule a user's duty for this week"""

    user = update.effective_user
    user_text = user.mention_markdown_v2()

    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    start_of_week = today - datetime.timedelta(days=today.weekday())

    mongo_db = setup_mongodb()
    duties = mongo_db["duties"]

    # Find this week's duty
    duty = duties.find_one({
        'user': user.id,
        # 'isCompleted': False,
        'date': { '$gte': start_of_week }
    }, sort=[('date', 1)])

    if duty is None:
        message = fr'{user_text} you have no laundry duty scheduled 🤨'
        return (message, None)

    # if 'isCompleted' in duty and duty['isCompleted']:
    #     message = fr'{user_text} you have already done laundry for this week 🤗'
    #     return (message, None)

    duty_date = duty['date']
    date = duty['date'].strftime("%A %-d %b")

    message = fr'{user_text} you have a laundry duty scheduled on {date}\. When would you like to do it instead\?'

    keyboard = []

    proposed_date = today
    end_of_window = today + datetime.timedelta(days=6)
    while proposed_date < end_of_window:
        day_string = proposed_date.strftime("%A %-d %b")
        date_string = proposed_date.strftime("%c")
        callback_data = fr"reschedule.{date_string}"
        print(callback_data)
        keyboard.append([InlineKeyboardButton(day_string, callback_data=callback_data)])
        proposed_date += datetime.timedelta(days=1)

    reply_markup = InlineKeyboardMarkup(keyboard)

    return (message, reply_markup)


def reschedule_callback(update, query_data):
    query = update.callback_query
    user = update.effective_user
    user_text = user.mention_markdown_v2()
    
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    start_of_week = today - datetime.timedelta(days=today.weekday())

    mongo_db = setup_mongodb()
    duties = mongo_db["duties"]

    # Find this week's duty
    duty = duties.find_one({
        'user': user.id,
        'date': { '$gte': start_of_week }
    }, sort=[('date', 1)])

    if duty is None:
        message = fr'{user_text} you have no laundry duty scheduled this week 🤨'
        query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)
        return None

    if 'isCompleted' in duty and duty['isCompleted']:
        message = fr'{user_text} you have already done laundry for this week 🤗'
        query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)
        return None

    duty_date = datetime.datetime.strptime(query_data, "%c")

    duties.find_one_and_update(
        { 'id': duty.id },
        { '$set':
            {
                'date': duty_date,
                'isMissed': False,
            }
        },
        upsert=True,
        return_document=pymongo.ReturnDocument.AFTER,
    )

    day = duty_date.strftime("%A")
    message = f"{user_text} has moved their laundry duty to *{day}* for this week 👌"
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)

def create_schedule(update: Update) -> str:
    """Create schedule with chat_id when the command /createschedule is issued."""

    chat_id = update.message.chat.id
    name = "🌀 Laundry duty roster 🧺 🌀"
    
    schedules = setup_mongodb()["schedules"]
    schedules.find_one_and_update(
        {
            'chat_id': chat_id,
        }, {
            '$setOnInsert': {
                'name': name,
                'chat_id': chat_id,
                'createdAt': datetime.datetime.now(),
                'interval': 'week'
            },
        },
        upsert=True
    )
    message = fr'{name} created'

    return message

def create_roster(update: Update, context: CallbackContext) -> str:
    """Create roster with chat_id when the command /createroster is issued."""

    chat_id = update.message.chat.id
    text = update.message.text
    if context:
        name = ' '.join(context.args)
        # breakpoint()
    else:
        name = text.replace('/createroster ', '', 1)

    if not name:
        name = 'OI'

    # rosters = setup_mongodb()["rosters"]
    # rosters.find_one_and_update(
    #     {
    #         'chat_id': chat_id,
    #     }, {
    #         '$setOnInsert': {
    #             'name': name,
    #             'chat_id': chat_id,
    #             'createdAt': datetime.datetime.now(),
    #             'interval': 'week'
    #         },
    #     },
    #     upsert=True
    # )
    message = fr'{name} created'

    update.message.reply_markdown_v2(
        text=message,
        reply_markup=ForceReply()
    )

    # return (message, ForceReply())

def show_duties(update: Update) -> str:
    """Send a message when the command /leave is issued."""
    message = ""

    mongo_db = setup_mongodb()
    duties = mongo_db["duties"]
    users = mongo_db["users"]

    # TODO: Filter to current month
    cursor = duties.find({}).sort('date')

    week_number = None
    for duty in cursor:
        user_text = get_name_from_user_id(users, duty['user'])

        if week_number is None:
            week_number = duty['date'].isocalendar()[1]
        elif duty['date'].isocalendar()[1] > week_number:
            message += '\-\n'
            week_number = duty['date'].isocalendar()[1]

        date = duty['date'].strftime("%a %d\/%m")
        message += fr'`{date}\:` {user_text}'
        if 'isCompleted' in duty and duty['isCompleted']:
            message += " ✅"
        message += "\n"

    message = message or "No duties created yet 🤷"
    return message

def mark_as_done(update: Update) -> str:
    """Mark user's duty as done when the command /done is issued."""

    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    # Get date window for duty
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    window_start = today - datetime.timedelta(days=3)
    window_end = today + datetime.timedelta(days=3)

    # Get mongodb collections
    mongo_db = setup_mongodb()
    duties = mongo_db["duties"]
    users = mongo_db["users"]

    # Find uncompleted duty in date window
    duty = duties.find_one({
        'user': user.id,
        'isCompleted': False,
        'date': { '$gte': window_start, '$lt': window_end }
    }, sort=[('date', 1)])

    duty_done = False

    if duty is None:
        # Check if user duty is on any day
        users = mongo_db["users"]
        user_dict = users.find_one({ 'id': user.id })

        if 'dutyDay' not in user_dict:
            duties.insert_one({
                'isCompleted': True,
                'date': today,
                'user': user.id,
            })
            duty_done = True
        # else: # TODO: Ad-hoc or overwrite duty
    else:
        # Update duty as completed
        duties.update_one(
            { '_id': duty['_id'] },
            { '$set': { 'isCompleted': True, 'isMissed': False } }
        )
        duty_done = True
        

    if duty_done:
        message = fr'✅ {user_text} just did laundry\! 👏 👏 👏'
    else:
        message = fr'🧐 No laundry duty scheduled for you today {user_text}\.'

    update.message.reply_markdown_v2(message, quote=False)

    if duty_done:
        send_gif(update)

    return None

def send_gif(update: Update):
    url = get_gif()
    update.message.reply_animation(animation=url, quote=False)

def add_to_waitlist(update):
    user = update.effective_user
    user_dict = { k: v for k, v in user.__dict__.items() if k in user_properties }
    user_dict['isWaiting'] = True
    user_dict['createdAt'] = datetime.datetime.now()

    waitlist = setup_mongodb()["waitlist"]

    result = waitlist.find_one_and_update(
        { 'id': user_dict['id'] },
        { '$setOnInsert': user_dict },
        upsert=True,
    )

    user_text = user.mention_markdown_v2()
    message = fr"👋 Hello {user_text}\! House Chores Bot is currently in closed beta\. Will let you know when it\'s ready for you 😃"
    return message

def user_next_duty(mongo_db, user_dict, update):
    """Get user's next duty date"""
    
    user_id = user_dict['id']
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)

    # mongo_db = setup_mongodb()
    duties = mongo_db["duties"]

    # Find next uncompleted duty
    duty = duties.find_one({
        'user': user_id,
        'isCompleted': False,
        'date': { '$gte': today }
    }, sort=[('date', 1)])

    if duty is None:
        return None

    duty_date = duty['date']
    user = User(**user_dict)
    user_text = user.mention_markdown_v2()

    if duty_date == today:
        message = fr'📅 {user_text}: Your laundry duty is today'
    elif duty_date == today + datetime.timedelta(days=1):
        message = fr'📅 {user_text}: Your next laundry duty is tomorrow'
    else:
        date = duty['date'].strftime("%A %-d %b")
        message = fr'📅 {user_text}: Your next laundry duty is on {date}'

    update.callback_query.message.reply_markdown_v2(message, quote=False)

def next_duty(update: Update) -> str:
    """Get next duty date and user when the command /nextduty is issued."""

    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)

    mongo_db = setup_mongodb()
    duties = mongo_db["duties"]
    users = mongo_db["users"]

    # Find next uncompleted duty
    duty = duties.find_one({
        'isCompleted': False,
        'date': { '$gte': today }
    }, sort=[('date', 1)])

    if duty is None:
        return fr'🧐 No more duties this week'

    user_text = get_name_from_user_id(users, duty['user'])
    duty_date = duty['date']

    if duty_date == today:
        return fr'📅 Next laundry duty is today by {user_text}'
    
    if duty_date == today + datetime.timedelta(days=1):
        return fr'📅 Next laundry duty is tomorrow by {user_text}'

    date = duty['date'].strftime("%A %-d %b")
    return fr'📅 Next laundry duty is on {date} by {user_text}'

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

# def check_missed_duties():
#     print('Running check_missed_duties')

#     now = datetime.datetime.now()
#     today = datetime.datetime(now.year, now.month, now.day)
#     window_end = today - datetime.timedelta(days=2)

#     result = duties.update_many(
#         {
#             'isCompleted': False,
#             'date': { '$lt': window_end }
#         },
#         {
#             '$set': {
#                 'isMissed': True
#             }
#         }
#     )

#     print('Missed duties: ' + result.raw_result)

def remind():
    # Get reminder window
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    window_start = today - datetime.timedelta(days=2)
    window_end = today + datetime.timedelta(days=0)

    # Find uncompleted duty
    mongo_db = setup_mongodb()
    duties = mongo_db["duties"]
    users = mongo_db["users"]
    duty = duties.find_one(
        {
            'isCompleted': False,
            'date': { '$gte': window_start, '$lte': window_end }
        },
        sort=[('date', 1)]
    )

    if duty is None:
        logger.info('No pending laundry duties between yesterday and tomorrow')
        return None

    user_text = get_name_from_user_id(users, duty['user'])
    duty_date = duty['date']

    if duty_date < today:
        return fr'💩 Oopsy daisy\, {user_text}\. Is the laundry piling up\? Send \/done if you\'ve already done the laundry\. If not\, it\'s not too late to do it today 😉'

    if duty_date > today:
        # return fr'🔔 {user_text} it\'s your turn to do laundry tomorrow'
        return None

    date_of_week = today.strftime('%A')
    return fr'{user_text} It\'s {date_of_week} and that means it\'s your turn to do laundry\! Remember to send \/done once you\'ve completed your chore 👍'


def get_chat_id():
    mongo_db = setup_mongodb()
    schedules = mongo_db["schedules"]
    schedule = schedules.find_one()
    if schedule is None:
        logger.warn("No schedule found")
        return None
    
    chat_id = schedule['chat_id']
    if chat_id is None:
        logger.warn("Empty chat_id")
        return None
    
    return chat_id