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
    # CallbackQueryHandler,
    # CommandHandler,
    ConversationHandler,
    # Filters,
    # MessageHandler,
    # Updater,
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
)

from helpers import (
    get_name_from_user_id,
    get_user_dict_from_user,
    get_chat_dict_from_chat,
    get_is_whitelisted,
    alert_creator,
    configure_telegram,
    week_days,
    week_days_short,
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

    keyboard = [roster_to_button(r, 'join') for r in rosters]
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
    print(data)
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

    callback_data_one = f'newchoresingle.{roster_id}.{duty_day}'
    callback_data_repeat = f'newchoredayrepeat.{roster_id}.{duty_day}'

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

def new_chore_single(update: Update, _: CallbackContext):
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
        }
    )

    roster_name = roster['name']
    duty_day_str = duty_date.strftime("%A %d/%m")

    message = fr"New chore *{roster_name}* added for {user_text} on *{duty_day_str}*\." + '\n'
    message += "\(I\'ll send a reminder in the morning 😉\)"
    
    logger.info('Edit message:\n' + message)
    query.edit_message_text(
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )