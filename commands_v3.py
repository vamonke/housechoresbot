import random
import requests
import pymongo
# import os
# import json
import datetime
from bson.objectid import ObjectId
from urllib.parse import urlencode

from telegram import (
    Update,
    # Bot,
    User,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    # KeyboardButton,
    # ReplyKeyboardMarkup,
    ForceReply,
    constants
)

from telegram.ext import (
    CallbackContext,
)

from mongo import (
    Chats,
    Rosters,
    Duties,
    Users,
)

from commands_v2 import (
    create_user,
    create_roster,
    roster_to_button,
    create_user_duties,
)

from helpers import (
    get_name_from_user_id,
    get_user_dict_from_user,
    get_chat_dict_from_chat,
    get_is_whitelisted,
    alert_creator,
    configure_telegram,
    add_user_to_roster,
    week_days,
    week_days_short,
    send_gif,
    duty_to_button,
)

from logger import logger

GIPHY_API_KEY = '1iI19SCF571Lt9CV2uNsXv3t1CzIRznM'

HOUSE_CHORES_BOT_ID = 1783406286
DUTY_ROSTER_BOT_ID = 1798724954

GET_ROSTER_NAME = 0
# JOIN_ROSTER = 1
# SELECT_DUTY_DAY = 2

WEEKS_IN_ADVANCE = 2

def add_command(update: Update, _: CallbackContext):
    """ Ask for roster name when the command /add is issued """
    # Get user
    user = update.effective_user
    create_user(user)

    # Get rosters
    chat_id = update.effective_chat.id
    rosters = Rosters.find({ 'chat_id': chat_id }, projection={ 'name': True })
    rosters = list(rosters)

    if not rosters:
        return create_roster(update, None)

    user_text = user.mention_markdown_v2()
    message = fr'{user_text} what\'s the name of the chore\?'

    keyboard = [roster_to_button(r, 'addexistingchore') for r in rosters]
    keyboard.append(
        [InlineKeyboardButton('✏️ New chore', callback_data='newchore')]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )

def new_chore_callback(update: Update, _: CallbackContext):
    """ Ask for new chore name """
    query = update.callback_query
    query.answer()
    query.message.delete()

    user = update.effective_user
    user_text = user.mention_markdown_v2()

    message = user_text + ' what\'s the name of the chore\?\n_\(e\.g\. laundry, mopping, trash\)_'

    logger.info('Reply message:\n' + message)
    update.effective_message.reply_markdown_v2(
        text=message,
        reply_markup=ForceReply(selective=True),
        quote=False,
    )

def new_chore_day_callback(update: Update, _: CallbackContext):
    query = update.callback_query
    query.answer()

    user = update.effective_user
    user_text = user.mention_markdown_v2()

    data = update.callback_query.data
    # print(data)
    _, roster_id, duty_day = data.split(".")
    duty_day = int(duty_day)
    
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)

    if roster is None:
        message = 'Oops! Something went wrong. Please try again in a few mins.'
        logger.info('Edit message:\n' + message)
        query.edit_message_text(text=message)
        return

    roster_name = roster['name']
    duty_day_str = week_days[duty_day]

    message = fr'New chore: *{roster_name}* on *{duty_day_str}*' + '\n'
    message += fr"{user_text} Does this chore repeat every {duty_day_str}\?"

    callback_data_one = f'addchoresingle.{roster_id}.{duty_day}'
    callback_data_repeat = f'addchoreweekly.{roster_id}.{duty_day}'

    keyboard = [
        [
            InlineKeyboardButton("Yes", callback_data=callback_data_repeat),
            InlineKeyboardButton("No", callback_data=callback_data_one),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Edit message:\n' + message)
    query.edit_message_text(
        text=message,
        reply_markup=reply_markup,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def cancel_callback(update: Update, _: CallbackContext):
    query = update.callback_query
    query.answer()
    query.message.delete()

def add_chore_single(update: Update, _: CallbackContext):
    query = update.callback_query
    query.answer()

    user = update.effective_user
    user_text = user.mention_markdown_v2()

    data = update.callback_query.data
    print(data)
    _, roster_id, duty_day = data.split(".")
    duty_day = int(duty_day)
    
    chat_id = update.effective_chat.id
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)

    if roster is None:
        message = 'Oops! Something went wrong. Please try again in a few mins.'
        logger.info('Edit message:\n' + message)
        query.edit_message_text(text=message)
        return

    # Get window to create duties
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)

    start_of_week = today - datetime.timedelta(days=today.weekday())
    duty_date = start_of_week + datetime.timedelta(days=duty_day)

    if duty_date.weekday() < today.weekday():
        duty_date += datetime.timedelta(weeks=1)

    # Run mongodb inserts
    Duties.insert_one(
        {
            'chat_id': chat_id,
            'roster_id': roster_id,
            'user': user.id,
            'isCompleted': False,
            'date': duty_date,
            'isAdhoc': True,
            'createdAt': now,
            'scheduledAt': duty_date,
        }
    )

    roster_name = roster['name']
    duty_day_str = duty_date.strftime("%A %d %b")
    week_day_str = duty_date.strftime("%a")

    message = fr"New chore added for {user_text}: *{roster_name}* on *{duty_day_str}*\." + '\n'
    message += fr"A reminder will be sent on {week_day_str} morning 😉"
    
    logger.info('Edit message:\n' + message)
    query.edit_message_text(
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def add_chore_weekly(update: Update, _: CallbackContext):
    query = update.callback_query
    query.answer()

    data = update.callback_query.data
    # print(data)
    _, roster_id, duty_day = data.split(".")
    duty_day = int(duty_day)

    # chat_id = update.effective_chat.id
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)

    if roster is None:
        message = 'Oops! Something went wrong. Please try again in a few mins.'
        logger.info('Edit message:\n' + message)
        query.edit_message_text(text=message)
        return
    
    # Add user to roster schedule
    user = update.effective_user
    user_text = user.mention_markdown_v2()
    user_dict = get_user_dict_from_user(user)
    user_dict['dutyDay'] = duty_day
    add_user_to_roster(user_dict, roster_id)

    # Create user duties
    create_user_duties(
        user_dict=user_dict,
        roster=roster,
        update=update
    )

    roster_name = roster['name']
    duty_day_str = week_days[duty_day]
    week_day_str = week_days_short[duty_day]

    message = fr"New chore added for {user_text}: *{roster_name}* every *{duty_day_str}*\." + '\n'
    message += fr"A reminder will be sent on {week_day_str} morning 😉"
    
    logger.info('Edit message:\n' + message)
    query.edit_message_text(
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def add_existing_chore_callback(update: Update, _: CallbackContext):
    """ Ask which day for exising chore """
    query = update.callback_query
    query.answer()

    user = update.effective_user
    user_text = user.mention_markdown_v2()

    data = update.callback_query.data
    _, roster_id = data.split(".")
    
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)

    if roster is None:
        message = 'Oops! Something went wrong. Please try again in a few mins.'
        logger.info('Edit message:\n' + message)
        query.edit_message_text(text=message)
        return

    user_text = user.mention_markdown_v2()

    roster_name = roster['name']
    message = fr'Add chore: *{roster_name}*' + '\n'
    message += fr'{user_text} Choose a day to perform this chore'

    keyboard = [
        [
            InlineKeyboardButton("Mon", callback_data=fr'newchoreday.{roster_id}.0'),
            InlineKeyboardButton("Tue", callback_data=fr'newchoreday.{roster_id}.1'),
            InlineKeyboardButton("Wed", callback_data=fr'newchoreday.{roster_id}.2'),
            InlineKeyboardButton("Thu", callback_data=fr'newchoreday.{roster_id}.3'),
            InlineKeyboardButton("Fri", callback_data=fr'newchoreday.{roster_id}.4'),
        ],
        [
            InlineKeyboardButton("Sat", callback_data=fr'newchoreday.{roster_id}.5'),
            InlineKeyboardButton("Sun", callback_data=fr'newchoreday.{roster_id}.6'),
        ],
        [
            InlineKeyboardButton("Cancel", callback_data=fr'cancel'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)

    query.edit_message_text(
        text=message,
        reply_markup=reply_markup,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def mark_as_done(update: Update, _: CallbackContext):
    """Mark user's duty as done when the command /done is issued."""
    # Get chat id
    chat_id = update.effective_chat.id

    # Get user
    user = update.effective_user
    user_id = user.id

    # Get date window for duty
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    # window_start = today - datetime.timedelta(days=2)
    # window_end = today + datetime.timedelta(days=1)
    window_start = today - datetime.timedelta(days=today.weekday())
    window_end = today + datetime.timedelta(days=6)

    # Find uncompleted duty in date window
    logger.info(f'Fetching incomplete duties with chat_id {chat_id} user_id {user_id} between {window_start} and {window_end}')
    incomplete_duties = Duties.find({
        'chat_id': chat_id,
        'user': user_id,
        'isCompleted': False,
        'date': { '$gte': window_start, '$lte': window_end }
    }, sort=[('date', 1)])
    incomplete_duties = list(incomplete_duties)
    logger.info(fr'Found incomplete duties {incomplete_duties}')

    if len(incomplete_duties) == 0:
        return ask_which_roster_done(update)

    if len(incomplete_duties) > 1:
        return ask_which_duty_done(update, incomplete_duties)
    
    # Update duty as completed
    duty = incomplete_duties[0]
    mark_duty_as_done(update=update, duty=duty)

def mark_duty_as_done(update: Update, duty: dict, roster: dict = None):
    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    # Get new duty date
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)

    duty_id = duty['_id']
    Duties.update_one(
        { '_id': duty_id },
        { '$set':
            {
                'isCompleted': True,
                'isMissed': False,
                'date': today,
                'completedAt': now,
            }
        }
    )

    message = fr'✅ {user_text} just completed a chore\! 👏 👏 👏'
    
    # Find roster
    if not roster:
        roster = Rosters.find_one(duty['roster_id'])

    if roster:
        roster_name = roster['name']
        message = fr'✅ {user_text} just completed *{roster_name}*\! 👏 👏 👏'
    
    query = update.callback_query
    if query:
        logger.info('Edit message:\n' + message)
        query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)
    else:
        logger.info('Reply message:\n' + message)
        update.message.reply_markdown_v2(message, quote=False)

    send_gif(update.effective_message)

def ask_which_duty_done(update: Update, incomplete_duties):
    """ Get rosters and send to user to select """

    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    # Get rosters
    roster_ids = [d['roster_id'] for d in incomplete_duties]
    rosters = Rosters.find({ '_id': { '$in': roster_ids } })
    rosters = list(rosters)
    rosters_dict = {r['_id']: r for r in rosters}

    for d in incomplete_duties:
        roster_id = d['roster_id']
        roster = rosters_dict[roster_id]
        roster_name = roster['name']
        d['name'] = roster_name

    message = fr'{user_text} which chore did you complete\?'
    keyboard = [duty_to_button(d, 'dutydone') for d in incomplete_duties]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )

def ask_which_roster_done(update: Update):
    """ Get rosters and send to user to select """

    # Get chat and roster ids
    chat_id = update.effective_chat.id
    rosters = Rosters.find({ 'chat_id': chat_id }, projection={ 'name': True })
    rosters = list(rosters)

    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    message = fr'{user_text} which chore did you complete\?'
    keyboard = [roster_to_button(r, 'rosterdone') for r in rosters]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)
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
    # TODO: Remove check for incomplete duty. Check has already been done.
    incomplete_duty = Duties.find_one({
        'roster_id': roster_id,
        'chat_id': chat_id,
        'user': user.id,
        'isCompleted': False,
        'date': { '$gte': window_start, '$lte': window_end }
    }, sort=[('date', 1)])

    if incomplete_duty:
        # Update duty as completed
        duty_id = incomplete_duty['_id']
        Duties.update_one(
            { '_id': duty_id },
            { '$set': {
                'isCompleted': True,
                'isMissed': False,
                'completedAt': now,
            } }
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
                    'completedAt': now,
                }
            },
            upsert=True,
        )

    # message = fr'🧐 No duty scheduled for you {user_text}\.'
    message = fr'✅ {user_text} just completed *{roster_name}*\! 👏 👏 👏'
    logger.info('Edit message:\n' + message)
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)
    
    send_gif(query.message)

def mark_duty_as_done_callback(update: Update, _: CallbackContext):
    """ Mark duty as done """
    query = update.callback_query
    query.answer()

    data = update.callback_query.data
    _, duty_id = data.split(".")
    duty_id = ObjectId(duty_id)
    duty = Duties.find_one(duty_id)

    mark_duty_as_done(
        update=update,
        duty=duty,
    )