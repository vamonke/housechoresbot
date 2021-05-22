# import random
# import requests
# import os
# import json
import pymongo
import datetime
from bson.objectid import ObjectId

from telegram import (
    Update,
    # Bot,
    # User,
    # Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
    constants
)

from telegram.ext import (
    CallbackContext,
)

from mongo import (
    # Chats,
    Rosters,
    Duties,
    # Users,
)

from commands import (
    create_user,
    create_roster,
    roster_to_button,
    create_user_duties,
)

from helpers import (
    # get_name_from_user_id,
    get_user_dict_from_user,
    # get_chat_dict_from_chat,
    # get_is_whitelisted,
    # alert_creator,
    # configure_telegram,
    add_user_to_roster,
    week_days,
    week_days_short,
    create_chat,
    # send_gif,
    # duty_to_button,
)

from logger import logger

WEEKS_IN_ADVANCE = 2
HOUSE_CHORES_BOT_ID = 1783406286
DUTY_ROSTER_BOT_ID = 1798724954

def add_command(update: Update, _: CallbackContext):
    """
        /add
        Get rosters and ask user to select roster to add chore to
        Receive: None
        Reply: Roster names
    """
    # Get user
    user = update.effective_user
    
    # Onboard user and chat
    create_chat(update)
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
        [InlineKeyboardButton('✏️ New chore', callback_data='addnewchore')]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )

def add_new_chore_callback(update: Update, _: CallbackContext):
    """
        /add -> [New Chore]
        Ask for new roster name
        Receive: None
        Reply: None
    """
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

def receive_roster_name(update: Update, _: CallbackContext):
    """Create roster with chat_id and name"""
    
    # Verify if message is reply to bot create_roster message

    # Check sender of create_roster message
    message = update.effective_message
    reply_to_message = message.reply_to_message
    user_to_reply_id = reply_to_message.from_user.id
    if user_to_reply_id not in [HOUSE_CHORES_BOT_ID, DUTY_ROSTER_BOT_ID]:
        return
    
    # Check content of create_roster message
    substring = 'what\'s the name of the chore?'
    message_to_reply = reply_to_message.text
    if substring not in message_to_reply:
        return

    name = update.message.text
    user = update.effective_user
    chat_id = update.message.chat.id

    logger.info(f"Creating roster {name} by {user.id}")
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

    user_text = user.mention_markdown_v2()

    message = fr'New chore: *{name}*' + '\n'
    message += fr'{user_text} Choose a day to perform this chore'

    roster_id = result['_id']

    keyboard = [
        [
            InlineKeyboardButton("Mon", callback_data=fr'addchoreday.{roster_id}.0'),
            InlineKeyboardButton("Tue", callback_data=fr'addchoreday.{roster_id}.1'),
            InlineKeyboardButton("Wed", callback_data=fr'addchoreday.{roster_id}.2'),
            InlineKeyboardButton("Thu", callback_data=fr'addchoreday.{roster_id}.3'),
            InlineKeyboardButton("Fri", callback_data=fr'addchoreday.{roster_id}.4'),
        ],
        [
            InlineKeyboardButton("Sat", callback_data=fr'addchoreday.{roster_id}.5'),
            InlineKeyboardButton("Sun", callback_data=fr'addchoreday.{roster_id}.6'),
        ],
        [
            InlineKeyboardButton("Cancel", callback_data=fr'cancel'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        quote=False,
        reply_markup=reply_markup
    )

def add_existing_chore_callback(update: Update, _: CallbackContext):
    """
        /add -> [Existing chore]
        Ask for day of week for chore to be added
        Receive: roster_id
        Reply: Weekdays/Cancel buttons
    """
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
            InlineKeyboardButton("Mon", callback_data=fr'addchoreday.{roster_id}.0'),
            InlineKeyboardButton("Tue", callback_data=fr'addchoreday.{roster_id}.1'),
            InlineKeyboardButton("Wed", callback_data=fr'addchoreday.{roster_id}.2'),
            InlineKeyboardButton("Thu", callback_data=fr'addchoreday.{roster_id}.3'),
            InlineKeyboardButton("Fri", callback_data=fr'addchoreday.{roster_id}.4'),
        ],
        [
            InlineKeyboardButton("Sat", callback_data=fr'addchoreday.{roster_id}.5'),
            InlineKeyboardButton("Sun", callback_data=fr'addchoreday.{roster_id}.6'),
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

def add_chore_day_callback(update: Update, _: CallbackContext):
    """
        /add ─┬─> [Existing chore] ───┬─> [Day]
              └─> [New chore] -> Name ┘
        Ask if chore is one-time or weekly
        Receive: roster_id, duty_day
        Reply: Yes/No buttons
    """
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

def add_chore_single(update: Update, _: CallbackContext):
    """
        /add ─┬─> [Existing chore] ───┬─> [Day] ─> [No]
              └─> [New chore] -> Name ┘
        Create single duty
        Receive: roster_id, duty_day
        Reply: None
    """
    query = update.callback_query
    query.answer()

    user = update.effective_user
    user_text = user.mention_markdown_v2()

    data = update.callback_query.data
    # print(data)
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

    print(f'duty_date {duty_date.weekday()}')
    print(f'today {today.weekday()}')

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
    """
        /add ─┬─> [Existing chore] ───┬─> [Day] ─> [Yes]
              └─> [New chore] -> Name ┘
        Add user to roster schedule and create weekly duties
        Receive: roster_id, duty_day
        Reply: None
    """

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
