import random
import requests
import pymongo
import os
import json
import datetime
from bson.objectid import ObjectId
from urllib.parse import urlencode

from telegram import (
    Update,
    Bot,
    User,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ForceReply,
    constants
)

from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    Filters,
    MessageHandler,
    Updater,
)

from mongo import (
    Chats,
    Schedules,
    Rosters,
    Duties,
    Users
)

from helpers import (
    get_name_from_user_id,
    get_user_dict_from_user,
)

from logger import logger

week_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
week_days_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

GIPHY_API_KEY = '1iI19SCF571Lt9CV2uNsXv3t1CzIRznM'

user_properties = [
    'id',
    'first_name',
    'last_name',
    'username',
    'is_bot',
    'language_code',
]

GET_ROSTER_NAME = 0
# JOIN_ROSTER = 1
# SELECT_DUTY_DAY = 2

WEEKS_IN_ADVANCE = 2

def start(update: Update, context: CallbackContext):
    """Return a message when the command /start is issued."""
    user = update.effective_user

    # TODO: Save (upsert) chat to Chats

    message =  fr'Hi {user.mention_markdown_v2()}\!'

    update.message.reply_markdown_v2(message)

def leave(update: Update):
    """Send a message when the command /leave is issued."""
    user = update.effective_user
    user_dict = get_user_dict_from_user(user)
    user_dict['modifiedAt'] = datetime.datetime.now()

    users = setup_mongodb()["users"]
    result = Users.find_one_and_update(
        { 'id': user_dict['id'] },
        { '$set': user_dict },
        upsert=True,
    )

    if result is None or result['isRemoved']:
        return fr'{user.mention_markdown_v2()} is already not in the duty roster'

    return fr'{user.mention_markdown_v2()} left'

def create_user_duties(user_dict: dict, roster: dict, update: Update):
    """Create duties for a user"""

    if user_dict is None or roster is None or 'dutyDay' not in user_dict:
        return

    # Get window to create duties
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    start_of_cycle = today - datetime.timedelta(days=today.weekday())
    end_of_cycle = start_of_cycle + datetime.timedelta(weeks=WEEKS_IN_ADVANCE)

    roster_id = roster['_id']

    # Remove future user duties from this roster
    Duties.delete_many(
        {
            'user': user_dict['id'],
            'roster_id': roster_id,
            'isCompleted': False,
            'date': { '$gte': today },
        }
    )

    # Get mongodb inserts
    requests = []
    day = user_dict['dutyDay']
    date = start_of_cycle + datetime.timedelta(days=day)
    while (date < end_of_cycle):
        if (date < today):
            date += datetime.timedelta(weeks=1)
            continue
        duty = {
        }
        # logger.info('duty', duty)
        request = pymongo.UpdateOne(
            {
                'user': user_dict['id'],
                'date': date,
                'roster_id': roster_id,
                'isCompleted': False,
            },
            {
                '$setOnInsert': {
                    'user': user_dict['id'],
                    'date': date,
                    'roster_id': roster_id,
                    'isCompleted': False,
                    'createdAt': now,
                }
            },
            upsert=True
        )
        requests.append(request)
        date += datetime.timedelta(weeks=1)

    # Run mongodb inserts
    result = Duties.bulk_write(requests)
    logger.info('result', result.bulk_api_result)

    user_next_duty(user_dict, roster, update)

# def create_duties():
#     """Create duties when the command /createduties is issued."""
#     now = datetime.datetime.now()
#     today = datetime.datetime(now.year, now.month, now.day)
#     start_of_cycle = today - datetime.timedelta(days=today.weekday())
#     end_of_cycle = start_of_cycle + datetime.timedelta(weeks=2)

#     requests = []

#     cursor = Users.find({ 'isRemoved': False }).sort('dutyDay')

#     for user_dict in cursor:
#         if 'dutyDay' in user_dict:
#             day = user_dict['dutyDay']
#             date = start_of_cycle + datetime.timedelta(days=day)
#             while (date < end_of_cycle):
#                 if (date < today):
#                     date += datetime.timedelta(weeks=1)
#                     continue
#                 duty = {
#                     'user': user_dict['id'],
#                     'date': date,
#                     'createdAt': now,
#                     'isCompleted': False,
#                 }
#                 request = pymongo.UpdateOne(
#                     duty,
#                     { '$setOnInsert': duty },
#                     upsert=True
#                 )
#                 requests.append(request)
#                 date += datetime.timedelta(weeks=1)


#     # print(requests)
#     result = Duties.bulk_write(requests)
#     logger.info('result', result.bulk_api_result)
    
#     # end_of_cycle_date = end_of_cycle.strftime("%-d %b %Y")
#     # message = f"{result.matched_count + result.upserted_count} duties created til {end_of_cycle_date}" # TODO: Fix count

#     # return message

def show_schedule(update: Update):
    """Send a message when the command /showschedule is issued."""

    message = ""

    schedule = Schedules.find_one()

    if schedule is None:
        message += fr"No schedule found" + "\n\n"
    else:
        schedule_name = schedule['name']
        message += fr"*{schedule_name}*" + "\n\n"

    days = ['' for _ in range(7)]
    anyday = None

    cursor = Users.find({ 'isRemoved': False }).sort('dutyDay')
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

def create_roster(update: Update, context: CallbackContext) -> int:
    """Ask for roster name when the command /createroster is issued."""

    if context and context.args:
        name = ' '.join(context.args)

    message = fr'\/createroster: What\'s the name of the chore\? \
_\(e\.g\. laundry, mopping, dishes\)_'
    update.message.reply_markdown_v2(
        text=message,
        reply_markup=ForceReply()
    )

    return GET_ROSTER_NAME

def receive_roster_name(update: Update, context: CallbackContext):
    """Create roster with chat_id and name"""

    chat_id = update.message.chat.id
    name = update.message.text
    user = update.effective_user

    result = Rosters.insert_one(
        {
            'name': name,
            'chat_id': chat_id,
            'createdAt': datetime.datetime.now(),
            'interval': 'week',
            'createdBy': user.id,
            'schedule': [],
        },
    )
    roster_id = result.inserted_id

    message = fr'New roster added: *{name}*\
To join the roster, hit *Join* below\!'

    button_text = fr'Join {name} roster'
    callback_data = fr'join.{roster_id}'
    keyboard = [[InlineKeyboardButton(button_text, callback_data=callback_data)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup
    )

    return ConversationHandler.END

def join_roster(update: Update, context: CallbackContext):
    """Let user select duty day for roster"""
    user = update.effective_user
    create_user(user)

    query = update.callback_query
    query.answer()

    data = update.callback_query.data
    roster_id = data.replace('join.', '')
    roster = Rosters.find_one(ObjectId(roster_id))

    if roster is None:
        message = 'Oops! This roster has been removed.'
        query.edit_message_text(text=message)
        return

    if query.message is None:
        message = fr'New roster added: *{name}*\
Send \/join to join the roster\!'
        query.edit_message_text(text=message)
        return

    roster_name = roster['name']
    message = fr'👋 Welcome to the *{roster_name}* roster, {user.mention_markdown_v2()}\! Which day do you wanna do your chore\?'
    keyboard = [
        [
            InlineKeyboardButton("Mon", callback_data=fr'addtoroster.{roster_id}.0'),
            InlineKeyboardButton("Tue", callback_data=fr'addtoroster.{roster_id}.1'),
            InlineKeyboardButton("Wed", callback_data=fr'addtoroster.{roster_id}.2'),
            InlineKeyboardButton("Thu", callback_data=fr'addtoroster.{roster_id}.3'),
            InlineKeyboardButton("Fri", callback_data=fr'addtoroster.{roster_id}.4'),
        ],
        [
            InlineKeyboardButton("Sat", callback_data=fr'addtoroster.{roster_id}.5'),
            InlineKeyboardButton("Sun", callback_data=fr'addtoroster.{roster_id}.6'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup
    )

def add_to_roster(update: Update, context: CallbackContext):
    """Add user to duty roster"""
    query = update.callback_query
    query.answer()

    data = update.callback_query.data
    data = data.replace('addtoroster.', '')
    roster_id, duty_day = data.split(".")
    roster = Rosters.find_one(ObjectId(roster_id))

    if roster is None:
        message = 'Oops! This roster has been removed.'
        query.edit_message_text(text=message)
        return

    user = update.effective_user
    user_dict = get_user_dict_from_user(user)
    duty_day = int(duty_day)
    user_dict['dutyDay'] = duty_day

    if any(u['id'] == user.id for u in roster['schedule']):
        # Update existing user in schedule
        result = Rosters.update_one(
            { '_id': ObjectId(roster_id) },
            { '$set':
                { "schedule.$[user]": user_dict },
            },
            array_filters=[{ "user.id": user_dict['id'] }],
        )
    else:
        # Add new user to schedule
        result = Rosters.update_one(
            { '_id': ObjectId(roster_id) },
            { '$addToSet':
                { "schedule": user_dict },
            },
        )

    logger.info(result.raw_result)

    day = week_days[duty_day]
    roster_name = roster['name']
    user_text = user.mention_markdown_v2()

    message = f"{user_text} has chosen to do *{roster_name}* on *{day}* 👌"
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)

    create_user_duties(
        user_dict=user_dict,
        roster=roster,
        update=update
    )

def create_user(user):
    """Create user with upsert."""
    user_dict = get_user_dict_from_user(user)
    user_dict['createdAt'] = datetime.datetime.now()

    result = Users.find_one_and_update(
        { 'id': user_dict['id'] },
        { '$setOnInsert': user_dict },
        upsert=True,
    )

def join(update: Update, context: CallbackContext):
    """ Select which roster to join """
    # 1. Get chat_id
    # 2. Get schedules
    # 3. Display schedules as buttons
    return

def show_duties(update: Update, context: CallbackContext):
    """Shows chat's roster duties for the week"""
    
    chat_id = update.effective_chat.id

    rosters = Rosters.find({ 'chat_id': chat_id }, projection={ 'name': True })
    rosters = list(rosters)
    roster_ids = list(map(lambda r: r['_id'], rosters))

    # Get date window for duties
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    start_of_week = today - datetime.timedelta(days=today.weekday())
    end_of_week = start_of_week + datetime.timedelta(weeks=1)

    cursor = Duties.find({
        'roster_id': { '$in': roster_ids },
        'date': { '$gte': start_of_week, '$lte': end_of_week }
    }).sort('date')
    duties = list(cursor)

    message = ''

    for roster in rosters:
        roster_duties = list(filter(lambda d: (d['roster_id'] == roster['_id']), duties))
        if roster_duties:
            roster_name = roster['name']
            message += fr'*{roster_name}*' + '\n'
            week_number = None
            for duty in roster_duties:
                user_text = get_name_from_user_id(duty['user'])

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
            message += "\n"

    message = message or "No duties created yet 🤷"

    update.message.reply_markdown_v2(text=message)

def mark_as_done(update: Update):
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

    # Find uncompleted duty in date window
    duty = Duties.find_one({
        'user': user.id,
        'isCompleted': False,
        'date': { '$gte': window_start, '$lt': window_end }
    }, sort=[('date', 1)])

    duty_done = False

    if duty is None:
        # Check if user duty is on any day
        user_dict = Users.find_one({ 'id': user.id })

        if 'dutyDay' not in user_dict:
            Duties.insert_one({
                'isCompleted': True,
                'date': today,
                'user': user.id,
            })
            duty_done = True
        # else: # TODO: Ad-hoc or overwrite duty
    else:
        # Update duty as completed
        Duties.update_one(
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

def user_next_duty(user_dict: dict, roster: dict, update: Update):
    """Get user's next duty date"""

    if (
        user_dict is None or \
        roster is None or \
        update.callback_query is None or \
        update.callback_query.message is None
    ):
        return

    user_id = user_dict['id']
    roster_id = roster['_id']
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)

    # Find next uncompleted duty
    duty = Duties.find_one({
        'user': user_id,
        'isCompleted': False,
        'roster_id': roster_id,
        'date': { '$gte': today }
    }, sort=[('date', 1)])

    if duty is None:
        return

    duty_date = duty['date']
    user = User(**user_dict)
    user_text = user.mention_markdown_v2()
    roster_name = roster['name']

    if duty_date == today:
        message = fr'📅 {user_text} you have a duty today: *{roster_name}*\. Send \/done once you\'ve completed your chore 👍'
        update.callback_query.message.reply_markdown_v2(message, quote=False)
    # elif duty_date == today + datetime.timedelta(days=1):
    #     message = fr'📅 {user_text}: Your next *{roster_name}* duty is tomorrow'
    # else:
    #     date = duty['date'].strftime("%A %-d %b")
    #     message = fr'📅 {user_text}: Your next laundry duty is on {date}'

    # update.callback_query.message.reply_markdown_v2(message, quote=False)

def next_duty(update: Update):
    """Get next duty date and user when the command /nextduty is issued."""

    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)

    # Find next uncompleted duty
    duty = Duties.find_one({
        'isCompleted': False,
        'date': { '$gte': today }
    }, sort=[('date', 1)])

    if duty is None:
        return fr'🧐 No more duties this week'

    user_text = get_name_from_user_id(duty['user'])
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

def remind():
    # Get reminder window
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    window_start = today - datetime.timedelta(days=2)
    window_end = today + datetime.timedelta(days=0)

    # Find uncompleted duty
    duty = Duties.find_one(
        {
            'isCompleted': False,
            'date': { '$gte': window_start, '$lte': window_end }
        },
        sort=[('date', 1)]
    )

    if duty is None:
        logger.info('No pending laundry duties between yesterday and tomorrow')
        return None

    user_text = get_name_from_user_id(duty['user'])
    duty_date = duty['date']

    if duty_date < today:
        return fr'💩 Oopsy daisy\, {user_text}\. Is the laundry piling up\? Send \/done if you\'ve already done the laundry\. If not\, it\'s not too late to do it today 😉'

    if duty_date > today:
        # return fr'🔔 {user_text} it\'s your turn to do laundry tomorrow'
        return None

    date_of_week = today.strftime('%A')
    return fr'{user_text} It\'s {date_of_week} and that means it\'s your turn to do laundry\! Remember to send \/done once you\'ve completed your chore 👍'


def get_chat_id():
    schedule = Schedules.find_one()
    if schedule is None:
        logger.warn("No schedule found")
        return None
    
    chat_id = schedule['chat_id']
    if chat_id is None:
        logger.warn("Empty chat_id")
        return None
    
    return chat_id

def cancel(update: Update, _: CallbackContext) -> int:
    user = update.message.from_user
    logger.info("User %s cancelled the conversation.", user.first_name)
    return ConversationHandler.END