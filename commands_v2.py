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
    Message,
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
    Users,
    Waitlist,
)

from helpers import (
    get_name_from_user_id,
    get_user_dict_from_user,
    get_chat_dict_from_chat,
    get_is_whitelisted,
    alert_creator,
)

from logger import logger

week_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
week_days_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

GIPHY_API_KEY = '1iI19SCF571Lt9CV2uNsXv3t1CzIRznM'

GET_ROSTER_NAME = 0
# JOIN_ROSTER = 1
# SELECT_DUTY_DAY = 2

WEEKS_IN_ADVANCE = 2

def start(update: Update, context: CallbackContext):
    """ Create chat and user """
    user = update.effective_user
    chat = update.effective_chat

    # chat_dict = get_chat_dict_from_chat(chat)
    # chat_dict['addedBy'] = user.id
    # chat_dict['isWhitelisted'] = True

    # Chats.update_one(
    #     { 'id': chat_dict['id'] },
    #     { '$set': chat_dict },
    #     upsert=True
    # )
    create_user(user)

    user_text = user.mention_markdown_v2()
    message =  fr'Hi {user_text}\! You have been specially selected as a beta tester for House Chores Bot\, a bot to help track household chores\. To begin\, send \/createroster\.' # For more info\, send \/help\.
    update.message.reply_markdown_v2(message, quote=False)

def check_whitelist(fn):
    def wrapper(update: Update, context: CallbackContext):
        is_whitelisted = get_is_whitelisted(update)
        if is_whitelisted:
            return fn(update, context)
        return send_beta_v2(update, context)

    return wrapper

def whitelist_user(update: Update, context: CallbackContext):
    """ Update chat and user """
    user = update.effective_user
    chat = update.effective_chat
    
    now = datetime.datetime.now()
    chat_dict = get_chat_dict_from_chat(chat)
    chat_dict['whitelistedBy'] = user.id
    chat_dict['whitelistedAt'] = now
    chat_dict['isWhitelisted'] = True

    Chats.update_one(
        { 'id': chat_dict['id'] },
        { '$set': chat_dict },
        upsert=True
    )

    user_dict = get_user_dict_from_user(user)
    user_dict['whitelistedAt'] = now
    user_dict['isWhitelisted'] = True

    Users.find_one_and_update(
        { 'id': user_dict['id'] },
        { '$set': user_dict },
        upsert=True,
    )

    message =  fr'🥳 You can now use House Chores Bot\! To begin\, send \/createroster\.'
    update.message.reply_markdown_v2(message, quote=False)

def delete_user_duties(user_id: int, roster_id: ObjectId):
    """ Remove future user duties from this roster """
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    Duties.delete_many(
        {
            'user': user_id,
            'roster_id': roster_id,
            'isCompleted': False,
            'date': { '$gte': today },
        }
    )

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
    user_id = user_dict['id']
    chat_id = update.effective_chat.id

    # Remove future user duties from this roster
    delete_user_duties(user_id, roster_id)

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
                'user': user_id,
                'date': date,
                'roster_id': roster_id,
                'isCompleted': False,
            },
            {
                '$setOnInsert': {
                    'user': user_id,
                    'date': date,
                    'roster_id': roster_id,
                    'chat_id': chat_id,
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

def show_rosters(update: Update, context: CallbackContext):
    """Shows rosters in chat"""

    # Get chat and roster ids
    chat_id = update.effective_chat.id
    rosters = Rosters.find({ 'chat_id': chat_id })
    rosters = list(rosters)

    if not rosters:
        message = "🤷 No rosters found\. Send \/createreoster to create a roster\."
        update.message.reply_markdown_v2(message, quote=False)
        return

    # breakpoint()
    message = ''

    for roster in rosters:
        roster_name = roster['name']
        message += fr'*{roster_name}*' + '\n'

        roster_users = roster['schedule']
        if not roster_users:
            message += fr'\(Roster is empty\)' + '\n'
        else:
            for user_dict in roster_users:
                user = User(**user_dict)
                user_text = user.mention_markdown_v2()
                duty_day = user_dict['dutyDay']
                day = week_days_short[duty_day]
                message += fr'`{day}\:` {user_text}'

                message += "\n"
        
        message += "\n"

    update.message.reply_markdown_v2(message, quote=False)

def create_roster(update: Update, context: CallbackContext) -> int:
    """Ask for roster name when the command /createroster is issued."""

    user = update.effective_user
    user_text = user.mention_markdown_v2()

    # message = 'What\'s the name of the chore\?\n_\(e\.g\. laundry, mopping, dishes\)_'
    message = user_text + ' what\'s the name of the chore\?\n_\(e\.g\. laundry, mopping, dishes\)_'

    update.message.reply_markdown_v2(
        text=message,
        reply_markup=ForceReply(selective=True),
        quote=False,
    )

    return GET_ROSTER_NAME

def receive_roster_name(update: Update, context: CallbackContext):
    """Create roster with chat_id and name"""

    chat_id = update.message.chat.id
    name = update.message.text
    user = update.effective_user

    roster = {
        'name': name,
        'chat_id': chat_id,
        'createdAt': datetime.datetime.now(),
        'interval': 'week',
        'createdBy': user.id,
        'schedule': [],
    }

    result = Rosters.find_one_and_update(
        {
            'name': name,
            'chat_id': chat_id,
        },
        { '$setOnInsert': roster },
        upsert=True,
        return_document=pymongo.ReturnDocument.AFTER,
    )

    roster_id = result['_id']

    message = fr'➕ New roster added: *{name}*' + '\n_Hit the button below to join the roster_'

    button_text = fr'Join roster: {name}'
    callback_data = fr'joinnewroster.{roster_id}'
    keyboard = [[InlineKeyboardButton(button_text, callback_data=callback_data)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_markdown_v2(
        text=message,
        quote=False,
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
    join_type, roster_id = data.split(".")
    roster = Rosters.find_one(ObjectId(roster_id))

    if roster is None:
        message = 'Oops! This roster has been removed.'
        query.edit_message_text(text=message)
        return

    is_new_roster = join_type == 'joinnewroster'

    # IDK when this happens but just in case lol
    if query.message is None:
        if is_new_roster:
            message = fr'New roster added: *{name}*' + '\nSend \/join to join the roster\!'
        else:
            message = fr'Oops\, something went wrong\!'
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

    if is_new_roster:
        query.message.reply_markdown_v2(
            text=message,
            reply_markup=reply_markup,
            quote=False,
        )
    else:
        query.edit_message_text(
            text=message,
            reply_markup=reply_markup,
            parse_mode=constants.PARSEMODE_MARKDOWN_V2,
        )

def add_to_roster(update: Update, context: CallbackContext):
    """Add user to duty roster"""
    query = update.callback_query
    query.answer()

    data = update.callback_query.data
    data = data.replace('addtoroster.', '')
    roster_id, duty_day = data.split(".")
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)

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
            { '_id': roster_id },
            { '$set':
                { "schedule.$[user]": user_dict },
            },
            array_filters=[{ "user.id": user_dict['id'] }],
        )
    else:
        # Add new user to schedule
        result = Rosters.update_one(
            { '_id': roster_id },
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

def create_user(user, whitelist=True):
    """Create user with upsert."""
    user_dict = get_user_dict_from_user(user)
    user_dict['createdAt'] = datetime.datetime.now()
    user_dict['isWhitelisted'] = whitelist

    result = Users.find_one_and_update(
        { 'id': user_dict['id'] },
        { '$setOnInsert': user_dict },
        upsert=True,
    )

def join_roster_select(update: Update, context: CallbackContext):
    """ Let user select which roster to join """
    # Get chat and roster ids
    chat_id = update.effective_chat.id
    rosters = Rosters.find({ 'chat_id': chat_id }, projection={ 'name': True })
    rosters = list(rosters)
    roster_ids = list(map(lambda r: r['_id'], rosters))

    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    message = fr'\/join: {user_text} which roster do you want to join\?'
    keyboard = [roster_to_button(r, 'join') for r in rosters]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )

def show_duties(update: Update, context: CallbackContext):
    """Shows chat's roster duties for the week"""
    
    # Get chat and roster ids
    chat_id = update.effective_chat.id
    rosters = Rosters.find({ 'chat_id': chat_id }, projection={ 'name': True })
    rosters = list(rosters)
    roster_ids = list(map(lambda r: r['_id'], rosters))

    # Get date window for duties
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    start_of_week = today - datetime.timedelta(days=today.weekday() + 1)
    end_of_week = start_of_week + datetime.timedelta(weeks=1)
    # end_of_week = today + datetime.timedelta(days=6)

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
                    # message += '\-\n'
                    week_number = duty['date'].isocalendar()[1]

                date = duty['date'].strftime("%a %d\/%m")
                message += fr'`{date}\:` {user_text}'

                if 'isCompleted' in duty and duty['isCompleted']:
                    message += " ✅"

                message += "\n"
            message += "\n"

    if message:
        message = 'This week\'s duties:\n' + message
    else:
        message = "🤷 No duties this week"

    update.message.reply_markdown_v2(message, quote=False)

def mark_as_done(update: Update, context: CallbackContext):
    """Mark user's duty as done when the command /done is issued."""

    # Get chat id
    chat_id = update.effective_chat.id

    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    # Get date window for duty
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    window_start = today - datetime.timedelta(days=2)
    window_end = today + datetime.timedelta(days=1)

    # Find uncompleted duty in date window
    incomplete_duties = Duties.find({
        'chat_id': chat_id,
        'user': user.id,
        'isCompleted': False,
        'date': { '$gte': window_start, '$lt': window_end }
    }, sort=[('date', 1)])
    incomplete_duties = list(incomplete_duties)

    if not incomplete_duties:
        ask_which_roster_done(update)
        return
    elif len(incomplete_duties) > 1:
        ask_which_roster_done(update)
        return
    
    # Update duty as completed
    duty = incomplete_duties[0]
    duty_id = duty['_id']
    Duties.update_one(
        { '_id': duty_id },
        { '$set': { 'isCompleted': True, 'isMissed': False } }
    )

    message = fr'✅ {user_text} just completed a duty\! 👏 👏 👏'

    # Find roster
    roster = Rosters.find_one(duty['roster_id'])
    if roster is not None:
        roster_name = roster['name']
        message = fr'✅ {user_text} just completed *{roster_name}*\! 👏 👏 👏'

    update.message.reply_markdown_v2(message, quote=False)
    send_gif(update.message)

def roster_to_button(roster, callback_text):
    button_text = roster['name']
    roster_id = roster['_id']
    callback_data = fr'{callback_text}.{roster_id}'
    return [InlineKeyboardButton(button_text, callback_data=callback_data)]

def ask_which_roster_done(update: Update):
    """ Get rosters and send to user to select """

    # Get chat and roster ids
    chat_id = update.effective_chat.id
    rosters = Rosters.find({ 'chat_id': chat_id }, projection={ 'name': True })
    rosters = list(rosters)
    roster_ids = list(map(lambda r: r['_id'], rosters))

    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    message = fr'\/done: {user_text} which chore did you complete\?'
    keyboard = [roster_to_button(r, 'rosterdone') for r in rosters]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )

def mark_roster_as_done(update: Update, _: CallbackContext):
    """ Find roster duty and mark it as done """
    query = update.callback_query
    query.answer()

    # Get chat id
    chat_id = update.effective_chat.id

    # Get roster
    data = query.data
    roster_id = data.replace('rosterdone.', '')
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)
    roster_name = roster['name']

    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    # Get date window for duty
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    window_start = today - datetime.timedelta(days=2)
    window_end = today + datetime.timedelta(days=1)

    # Find uncompleted duty in date window
    incomplete_duty = Duties.find_one({
        'roster_id': roster_id,
        'chat_id': chat_id,
        'user': user.id,
        'isCompleted': False,
        'date': { '$gte': window_start, '$lt': window_end }
    }, sort=[('date', 1)])

    if incomplete_duty:
        # Update duty as completed
        duty_id = incomplete_duty['_id']
        Duties.update_one(
            { '_id': duty_id },
            { '$set': { 'isCompleted': True, 'isMissed': False } }
        )
    else:
        # Insert completed duty
        Duties.find_one_and_update(
            {
                'user': user.id,
                'chat_id': chat_id,
                'roster_id': roster_id,
                'date': today,
            },
            { '$setOnInsert':
                {
                    'chat_id': chat_id,
                    'roster_id': roster_id,
                    'user': user.id,
                    'isCompleted': True,
                    'date': today,
                    'isAdhoc': True,
                    'createdAt': now,
                }
            },
            upsert=True,
        )

    # message = fr'🧐 No duty scheduled for you {user_text}\.'
    message = fr'✅ {user_text} just completed *{roster_name}*\! 👏 👏 👏'
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)
    
    send_gif(query.message)

def send_gif(message: Message):
    url = get_gif()
    message.reply_animation(animation=url, quote=False)

def leave_roster(update: Update, context: CallbackContext):
    """Remove user from roster and remove duties"""
    user = update.effective_user

    query = update.callback_query
    query.answer()

    data = update.callback_query.data
    _, roster_id = data.split(".")
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)

    if roster is None:
        message = 'Oops! This roster has been removed.'
        query.edit_message_text(text=message)
        return

    user = update.effective_user
    user_dict = get_user_dict_from_user(user)
    user_id = user_dict['id']

    if any(u['id'] == user.id for u in roster['schedule']):
        # Remove existing user from schedule
        Rosters.update_one(
            { '_id': roster_id },
            { '$pull':
                { 'schedule': { 'id': user_id } }
            },
        )

    # Remove user duties
    delete_user_duties(user_id=user_id, roster_id=roster_id)

    roster_name = roster['name']
    user_text = user.mention_markdown_v2()
    message = f"👋 {user_text} has left roster: *{roster_name}*"
    
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)
    
def leave_roster_select(update: Update, context: CallbackContext):
    """Let user select which roster to leave"""
    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()
    user_id = user.id

    # Get chat id
    chat_id = update.effective_chat.id

    rosters = Rosters.find(
        {
            'chat_id': chat_id,
            'schedule': {
                '$elemMatch': {
                    'id': user_id
                } 
            }
        },
        projection={ 'name': True }
    )
    rosters = list(rosters)
    roster_ids = list(map(lambda r: r['_id'], rosters))

    if not rosters:
        message = fr'{user_text} you are not in any rosters 🧐'
        update.message.reply_markdown_v2(message, quote=False)
        return

    message = fr'\/leave: {user_text} which roster do you want to leave\?'
    keyboard = [roster_to_button(r, 'leave') for r in rosters]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )

def add_to_waitlist(update):
    # Add user
    user = update.effective_user
    user_id = user.id
    create_user(user, whitelist=False)

    # Add chat
    chat = update.effective_chat
    chat_dict = get_chat_dict_from_chat(chat)
    chat_dict['addedBy'] = user_id
    chat_dict['createdAt'] = datetime.datetime.now()
    chat_dict['isWhitelisted'] = False

    Chats.update_one(
        { 'id': chat_dict['id'] },
        { '$set': chat_dict },
        upsert=True
    )

    user_text = user.mention_markdown_v2()
    message = fr"👋 Hello {user_text}\! House Chores Bot is currently in closed beta\. Will let you know when it\'s ready for you 😃"

    update.message.reply_markdown_v2(message, quote=False)

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

def send_beta_v2(update: Update, _: CallbackContext):
    add_to_waitlist(update)

    user_text = update.effective_user.mention_markdown_v2()
    message = fr"{user_text} spoke to HouseChoresBot\! 😀"
    alert_creator(message)

    return ConversationHandler.END

    # if update.message is not None and message is not None:
    #     update.message.reply_markdown_v2(message, quote=False)
    #     logger.info(message)

    # message = fr"Someone spoke to HouseChoresBot\! ❓"
    # if update.effective_user is not None:
    #     user_text = update.effective_user.mention_markdown_v2()
    #     message = fr"{user_text} spoke to HouseChoresBot\! 😀"

    # alert_creator(message)

def save_chat_group(update: Update, _: CallbackContext):
    user = update.effective_user
    user_id = user.id
    user_text = user.mention_markdown_v2()

    chat = update.effective_chat
    chat_id = chat.id
    chat_title = chat.title
    
    my_chat_member = update.my_chat_member
    from_user = my_chat_member.from_user
    new_chat_member = my_chat_member.new_chat_member
    status = new_chat_member.status

    message = fr'Bot status\: `{status}` in {chat_title} by {user_text}'
    alert_creator(message)

    if status is telegram.constants.CHATMEMBER_MEMBER:
        chat_dict = get_chat_dict_from_chat(chat)
        chat_dict['addedBy'] = user_id
        # chat_dict['isWhitelisted'] = True
        Chats.update_one(
            { 'id': chat_dict['id'] },
            { '$set': chat_dict },
            upsert=True
        )
    elif status in [telegram.constants.CHATMEMBER_KICKED, telegram.constants.CHATMEMBER_LEFT]:
        Chats.update_one(
            { 'id': chat_id },
            { '$set': { 'isRemoved': True } },
        )

    # create_user(user)