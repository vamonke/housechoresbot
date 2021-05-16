import random
import requests
import pymongo
import time
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
    Schedules,
    Rosters,
    Duties,
    Users,
    # Waitlist,
)

from helpers import (
    get_name_from_user_id,
    get_user_dict_from_user,
    get_chat_dict_from_chat,
    get_is_whitelisted,
    alert_creator,
    configure_telegram,
)

from logger import logger

week_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
week_days_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

GIPHY_API_KEY = '1iI19SCF571Lt9CV2uNsXv3t1CzIRznM'

HOUSE_CHORES_BOT_ID = 1783406286
DUTY_ROSTER_BOT_ID = 1798724954

GET_ROSTER_NAME = 0
# JOIN_ROSTER = 1
# SELECT_DUTY_DAY = 2

WEEKS_IN_ADVANCE = 2

INTRO_MESSAGE = 'I\'m a bot that helps you keep track of household chores\.\n\nYou can create chores\, schedule weekly duties and mark them as done\. I also send reminders so you won\'t forget about them 😉\n\nGet started by sending \/addchore to create a chore\.'

def start(update: Update, _: CallbackContext):
    """ Create chat and user """
    user = update.effective_user
    # chat = update.effective_chat

    # chat_dict = get_chat_dict_from_chat(chat)
    # chat_dict['addedBy'] = user.id
    # chat_dict['isWhitelisted'] = True

    # Chats.update_one(
    #     { 'id': chat_dict['id'] },
    #     { '$set': chat_dict },
    #     upsert=True
    # )
    create_user(user)

    # user_text = user.mention_markdown_v2()
    message = INTRO_MESSAGE
    # For more info\, send \/help\.
    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(message, quote=False)

def check_whitelist(fn):
    def wrapper(update: Update, context: CallbackContext):
        is_whitelisted = get_is_whitelisted(update)
        if is_whitelisted:
            logger.info(fn.__name__)
            return fn(update, context)
        
        logger.info('User not whitelisted. Sending beta message.')
        return send_beta_v2(update, context)

    return wrapper

def whitelist_user(update: Update, _: CallbackContext):
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

    message =  fr'🥳 You can now use House Chores Bot'

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(message, quote=False)

    start(update, None)

def delete_user_duties(user_id: int, roster_id: ObjectId):
    """ Remove future user duties from this roster """
    logger.info(fr'Removing duties with user_id {user_id} and roster_id {roster_id}')
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    result = Duties.delete_many(
        {
            'user': user_id,
            'roster_id': roster_id,
            'isCompleted': False,
            'date': { '$gte': today },
        }
    )
    logger.info('Bulk delete duties result:')
    logger.info(result.raw_result)

def delete_roster_duties(roster_id: ObjectId):
    """ Remove all duties from this roster """
    logger.info(fr'Removing duties from roster_id {roster_id}')
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    result = Duties.delete_many(
        {
            'roster_id': roster_id,
            'isCompleted': False,
            'date': { '$gte': today },
        }
    )
    logger.info('Bulk delete duties result:')
    logger.info(result.raw_result)

def create_user_duties(user_dict: dict, roster: dict, update: Update):
    """Create duties for a user"""

    if user_dict is None or roster is None or 'dutyDay' not in user_dict:
        logger.warn("Missing arguments")
        return

    roster_id = roster['_id']
    user_id = user_dict['id']
    chat_id = update.effective_chat.id

    logger.info(fr'Creating duties with user_id {user_id} and roster_id {roster_id}')

    # Remove future user duties from this roster
    # delete_user_duties(user_id, roster_id)

    # Get window to create duties
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    start_of_cycle = today - datetime.timedelta(days=today.weekday())
    end_of_cycle = start_of_cycle + datetime.timedelta(weeks=WEEKS_IN_ADVANCE)

    logger.info(fr'Start of cycle: {start_of_cycle} End of cycle: {end_of_cycle}')

    # Get mongodb inserts
    requests = []
    day = user_dict['dutyDay']
    date = start_of_cycle + datetime.timedelta(days=day)
    while (date < end_of_cycle):
        # if (date < today):
        #     date += datetime.timedelta(weeks=1)
        #     continue
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
    logger.info('Bulk create duties result:')
    logger.info(result.bulk_api_result)

    time.sleep(1) # Wait for 1 second
    user_next_duty(user_dict, roster, update)

def send_chores_tip(update: Update):
    """ Send /chores tiip """
    
    message = '💡 Tip: Send /chores to view this week\'s chores'
    update.effective_message.reply_markdown_v2(message, quote=False)

def show_rosters(update: Update, _: CallbackContext):
    """Shows rosters in chat"""

    # Get chat and roster ids
    chat_id = update.effective_chat.id
    rosters = Rosters.find({ 'chat_id': chat_id })
    rosters = list(rosters)

    if not rosters:
        message = r"🤷 No chores found\. Send \/addchore to create a weekly chore\."
        logger.info('Reply message:\n' + message)
        update.message.reply_markdown_v2(message, quote=False)
        return

    message = ''

    for roster in rosters:
        roster_name = roster['name']
        message += fr'*{roster_name}*' + '\n'

        roster_users = roster['schedule']
        if not roster_users:
            message += fr'\(Empty\)' + '\n'
        else:
            for user_dict in roster_users:
                user = User(**user_dict)
                user_text = user.mention_markdown_v2()
                duty_day = user_dict['dutyDay']
                day = week_days_short[duty_day]
                message += fr'`{day}\:` {user_text}'

                message += "\n"
        
        message += "\n"

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(message, quote=False)

def create_roster(update: Update, _: CallbackContext) -> int:
    """Ask for roster name when the command /addchore is issued."""

    user = update.effective_user
    user_text = user.mention_markdown_v2()

    message = user_text + ' what\'s the name of the chore\?\n_\(e\.g\. laundry, mopping, trash\)_'

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        reply_markup=ForceReply(selective=True),
        quote=False,
    )

    return GET_ROSTER_NAME

def receive_roster_name(update: Update, _: CallbackContext):
    """Create roster with chat_id and name"""

    chat_id = update.message.chat.id
    
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

    message = fr'➕ New chore created: *{name}*'
    logger.info('Reply message:\n' + message)

    roster_id = result['_id']
    button_text = fr'Select day'
    callback_data = fr'joinnewroster.{roster_id}'
    keyboard = [[InlineKeyboardButton(button_text, callback_data=callback_data)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_markdown_v2(
        text=message,
        quote=False,
        reply_markup=reply_markup
    )

    # update.message.reply_markdown_v2(message, quote=False)

    # roster['_id'] = roster_id
    # time.sleep(1)
    # new_roster_follow_up(update, roster)

def new_roster_follow_up(update, roster):
    roster_name = roster['name']
    roster_id = roster['_id']
    message = fr'👋 Hey folks\! Pick which day\(s\) of the week you want to do\: *{roster_name}*'
    keyboard = [
        [
            InlineKeyboardButton("Mon", callback_data=fr'addtonewroster.{roster_id}.0'),
            InlineKeyboardButton("Tue", callback_data=fr'addtonewroster.{roster_id}.1'),
            InlineKeyboardButton("Wed", callback_data=fr'addtonewroster.{roster_id}.2'),
            InlineKeyboardButton("Thu", callback_data=fr'addtonewroster.{roster_id}.3'),
            InlineKeyboardButton("Fri", callback_data=fr'addtonewroster.{roster_id}.4'),
        ],
        [
            InlineKeyboardButton("Sat", callback_data=fr'addtonewroster.{roster_id}.5'),
            InlineKeyboardButton("Sun", callback_data=fr'addtonewroster.{roster_id}.6'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )

def join_roster(update: Update, _: CallbackContext):
    """ /join: Let user select duty day for roster """
    user = update.effective_user
    user_id = user.id
    create_user(user)

    query = update.callback_query
    query.answer()

    data = update.callback_query.data
    join_type, roster_id = data.split(".")
    roster = Rosters.find_one(ObjectId(roster_id))

    is_join_new_roster = join_type == 'joinnewroster'

    if roster is None:
        message = 'Oops! This chore has been removed. You can create a new weekly chore by sending /addchore.'
        logger.info('Edit message:\n' + message)
        query.edit_message_text(text=message)
        return

    # IDK when this happens but just in case lol
    if query.message is None:
        message = fr'Oops\, something went wrong\!'
        logger.info('Edit message:\n' + message)
        query.edit_message_text(text=message)
        return

    roster_name = roster['name']
    roster_schedule = roster['schedule']

    message = ''
    user_already_in_roster = False

    if roster_schedule:
        message += fr'*{roster_name}*' + "\n"

    for user_schedule in sorted(roster_schedule, key=lambda us: us['dutyDay']):
        roster_user = User(**user_schedule)
        user_text = roster_user.mention_markdown_v2()
        duty_day = user_schedule['dutyDay']
        day = week_days_short[duty_day]
        message += fr'`{day}\:` {user_text}' + "\n"

        if roster_user.id == user_id:
            user_already_in_roster = True

    if user_already_in_roster:
        message += '\n' + fr'{user.mention_markdown_v2()} which additional day do you wanna do *{roster_name}*\?'
    else:
        message += '\n' + fr'{user.mention_markdown_v2()} which day do you wanna do\: *{roster_name}*\?'

    selected_duty_days = [us['dutyDay'] for us in roster_schedule]

    weekday_buttons = []
    for (i, weekday) in enumerate(week_days_short[:5]):
        if i in selected_duty_days:
            continue
        weekday_buttons.append(
            InlineKeyboardButton(weekday, callback_data=fr'addtoroster.{roster_id}.{i}')
        )

    weekend_buttons = []
    for (i, weekend) in enumerate(week_days_short[-2:]):
        day_of_week = i + 5
        if day_of_week in selected_duty_days:
            continue
        weekend_buttons.append(
            InlineKeyboardButton(weekend, callback_data=fr'addtoroster.{roster_id}.{day_of_week}')
        )

    extra_buttons = []
    extra_buttons.append(
        InlineKeyboardButton("Cancel", callback_data=fr'addtoroster.{roster_id}.-2')
    )

    keyboard = [weekday_buttons, weekend_buttons, extra_buttons]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if is_join_new_roster:
        logger.info('Callback query message:\n' + message)
        update.callback_query.message.reply_markdown_v2(
            text=message,
            reply_markup=reply_markup,
            quote=False,
        )
    else:
        logger.info('Edit message:\n' + message)
        query.edit_message_text(
            text=message,
            reply_markup=reply_markup,
            parse_mode=constants.PARSEMODE_MARKDOWN_V2,
        )

def add_to_new_roster(update: Update, _: CallbackContext):
    """Add user to new duty roster"""
    query = update.callback_query
    query.answer()

    user = update.effective_user
    logger.info(f"Create user {user.id}")
    create_user(user)

    data = update.callback_query.data
    _, roster_id, duty_day = data.split(".")
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)

    if roster is None:
        logger.info(f'Tried to add user to roster {roster_id} but the roster has been removed')
        message = 'Oops! This chore has been removed. You can create a new weekly chore by sending /addchore.'
        logger.info('Edit message:\n' + message)
        query.edit_message_text(text=message)
        return

    user = update.effective_user
    user_id = user.id
    duty_day = int(duty_day)
    user_dict = get_user_dict_from_user(user)
    user_dict['dutyDay'] = duty_day

    logger.info(fr'Adding user {user_id} to roster {roster_id}')

    roster_schedule = roster['schedule']
    user_ids = [us['id'] for us in roster_schedule]

    is_remove_from_roster = duty_day == -1

    if is_remove_from_roster:
        logger.info(fr'Removing user {user_id} from roster {roster_id}')
        delete_user_duties(user_id=user_id, roster_id=roster_id) # Just in case

        if user_id not in user_ids:
            logger.info(fr'User {user_id} not in roster {roster_id} schedule. Ignoring.')
            return

        # Remove existing user day in schedule
        roster = Rosters.find_one_and_update(
            { '_id': roster_id },
            { '$pull':
                { 'schedule': { 'id': user_id } }
            },
            return_document=pymongo.ReturnDocument.AFTER,
        )
    elif any((u['dutyDay'] == duty_day and u['id'] == user_dict['id']) for u in roster_schedule):
        # result = Rosters.update_one(
        #     { '_id': roster_id },
        #     { '$set':
        #         { "schedule.$[user]": user_dict },
        #     },
        #     array_filters=[{ "user.id": user_dict['id'] }],
        # )
        logger.error('Duty day clash!')
        # message = 'Oops! Something went wrong. Please try again later'
        # logger.info('Edit message:\n' + message)
        # query.edit_message_text(text=message)
        # return
    else:
        # Add new user to schedule
        roster = Rosters.find_one_and_update(
            { '_id': roster_id },
            { '$addToSet':
                { "schedule": user_dict },
            },
            return_document=pymongo.ReturnDocument.AFTER,
        )

    roster_name = roster['name']
    roster_schedule = roster['schedule']

    message = fr'👋 Hey folks\! Pick which day\(s\) of the week you want to do\: *{roster_name}*' + '\n\n'

    for user_schedule in sorted(roster_schedule, key=lambda us: us['dutyDay']):
        user = User(**user_schedule)
        user_text = user.mention_markdown_v2()
        duty_day = user_schedule['dutyDay']
        day = week_days_short[duty_day]
        message += fr'`{day}\:` {user_text}' + "\n"

    selected_duty_days = [us['dutyDay'] for us in roster_schedule]

    weekday_buttons = []
    for (i, weekday) in enumerate(week_days_short[:5]):
        if i in selected_duty_days:
            continue
        weekday_buttons.append(
            InlineKeyboardButton(weekday, callback_data=fr'addtonewroster.{roster_id}.{i}')
        )

    weekend_buttons = []
    for (i, weekend) in enumerate(week_days_short[-2:]):
        day_of_week = i + 5
        if day_of_week in selected_duty_days:
            continue
        weekend_buttons.append(
            InlineKeyboardButton(weekend, callback_data=fr'addtonewroster.{roster_id}.{day_of_week}')
        )

    if selected_duty_days:
        weekend_buttons.append(
            InlineKeyboardButton("None", callback_data=fr'addtonewroster.{roster_id}.-1')
        )

    keyboard = [weekday_buttons, weekend_buttons]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Edit message:\n' + message)
    query.edit_message_text(
        text=message,
        reply_markup=reply_markup,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2
    )

    if not is_remove_from_roster:
        create_user_duties(
            user_dict=user_dict,
            roster=roster,
            update=update
        )
        if len(roster['schedule']) == 1:
            time.sleep(1) # Wait for 1 second
            send_chores_tip(update)

def add_to_roster(update: Update, _: CallbackContext):
    """Add user to duty roster"""
    query = update.callback_query
    query.answer()

    data = update.callback_query.data
    data = data.replace('addtoroster.', '')
    roster_id, duty_day = data.split(".")
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)

    if roster is None:
        message = 'Oops! This chore has been removed. You can create a new weekly chore by sending /addchore.'
        logger.info('Edit message:\n' + message)
        query.edit_message_text(text=message)
        return

    user = update.effective_user
    user_id = user.id
    user_dict = get_user_dict_from_user(user)
    duty_day = int(duty_day)
    user_dict['dutyDay'] = duty_day

    roster_schedule = roster['schedule']
    user_ids = [us['id'] for us in roster_schedule]

    is_remove_from_roster = duty_day == -1
    is_cancel = duty_day == -2

    if is_cancel:
        logger.info('Cancelled. Deleting message')
        update.callback_query.message.delete()
        return
    elif is_remove_from_roster:
        logger.info(fr'Removing user {user_id} from roster {roster_id}')
        delete_user_duties(user_id=user_id, roster_id=roster_id) # Just in case

        if user_id not in user_ids:
            logger.info(fr'User {user_id} not in roster {roster_id} schedule. Ignoring.')
            return

        # Remove existing user day in schedule
        roster = Rosters.find_one_and_update(
            { '_id': roster_id },
            { '$pull':
                { 'schedule': { 'id': user_id } }
            },
            return_document=pymongo.ReturnDocument.AFTER,
        )
    elif any((u['dutyDay'] == duty_day and u['id'] == user_dict['id']) for u in roster_schedule):
        logger.error('Duty day clash!')
    else:
        # Add user to schedule
        roster = Rosters.find_one_and_update(
            { '_id': roster_id },
            { '$addToSet':
                { "schedule": user_dict },
            },
            return_document=pymongo.ReturnDocument.AFTER,
        )

    roster_schedule = roster['schedule']
    user_roster_schedule = filter(lambda us: us['id'] == user_id, roster_schedule)
    duty_days_long = [("*" + week_days[us['dutyDay']] + "*") for us in user_roster_schedule]
    days_str = ", ".join(duty_days_long)
    roster_name = roster['name']
    user_text = user.mention_markdown_v2()

    if days_str:
        message = f"{user_text} has chosen to do *{roster_name}* on {days_str} 👌"
        message += "\nI\'ll send a reminder in the morning so you won\'t miss it\."
    else:
        message = f"{user_text} has been removed from *{roster_name}*"

    logger.info('Edit message:\n' + message)
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)

    if is_remove_from_roster:
        delete_user_duties(user_id=user_id, roster_id=roster_id)
    else:
        create_user_duties(
            user_dict=user_dict,
            roster=roster,
            update=update
        )

    if days_str:
        time.sleep(2)
        send_chores_tip(update)

def create_user(user, whitelist=True):
    """Create user with upsert."""
    user_dict = get_user_dict_from_user(user)
    user_dict['createdAt'] = datetime.datetime.now()
    user_dict['isWhitelisted'] = whitelist

    logger.info(f"Upsert user {user_dict}")
    Users.find_one_and_update(
        { 'id': user_dict['id'] },
        { '$setOnInsert': user_dict },
        upsert=True,
    )

def join_roster_select(update: Update, _: CallbackContext):
    """ Let user select which roster to join """
    # Get chat and roster ids
    chat_id = update.effective_chat.id
    rosters = Rosters.find({ 'chat_id': chat_id }, projection={ 'name': True })
    rosters = list(rosters)

    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    message = fr'{user_text} which chore do you want to do\?'
    keyboard = [roster_to_button(r, 'join') for r in rosters]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )

def show_duties(update: Update, _: CallbackContext):
    """Shows chat's roster duties for the week"""

    # Get chat and roster ids
    chat_id = update.effective_chat.id
    logger.info(fr'Fetching rosters from chat {chat_id}')
    rosters = Rosters.find({ 'chat_id': chat_id }, projection={ 'name': True })
    rosters = list(rosters)
    roster_ids = list(map(lambda r: r['_id'], rosters))

    # Get date window for duties
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    start_of_week = today - datetime.timedelta(days=today.weekday())
    end_of_week = start_of_week + datetime.timedelta(weeks=1)
    # end_of_week = today + datetime.timedelta(days=6)

    logger.info(f'Fetching duties between {start_of_week} and {end_of_week}')
    cursor = Duties.find({
        'roster_id': { '$in': roster_ids },
        'date': { '$gte': start_of_week, '$lte': end_of_week }
    }).sort('date')
    duties = list(cursor)
    logger.info(fr'Found duties {duties}')

    duty_date_dict = {}

    for roster in rosters:
        roster_duties = list(filter(lambda d: (d['roster_id'] == roster['_id']), duties))
        if roster_duties:
            roster_name = roster['name']
            for duty in roster_duties:
                user_text = get_name_from_user_id(duty['user'])
                duty_line = fr'\- {roster_name}\: {user_text}'

                if 'isCompleted' in duty and duty['isCompleted']:
                    duty_line += " ✅"

                date = duty['date']
                if date in duty_date_dict:
                    duty_date_dict[date].append(duty_line)
                else:
                    duty_date_dict[date] = [duty_line]

    message = ''

    for date in sorted(duty_date_dict):
        date_str = date.strftime("%a %d/%m")
        if today == date:
            date_str += r' `\(Today\)`'
        message += f"*{date_str}*" + "\n"
        duties = duty_date_dict[date]
        message += "\n".join(duties)
        message += "\n\n"

    if message:
        message = "This week\'s chores\n\n" + message
    else:
        message = "🤷 No chores this week"

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(message, quote=False)

def mark_as_done(update: Update, _: CallbackContext):
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
    logger.info(f'Fetching incomplete duties with chat_id {chat_id} user_id {user.id} between {window_start} and {window_end}')
    incomplete_duties = Duties.find({
        'chat_id': chat_id,
        'user': user.id,
        'isCompleted': False,
        'date': { '$gte': window_start, '$lte': window_end }
    }, sort=[('date', 1)])
    incomplete_duties = list(incomplete_duties)
    logger.info(fr'Found incomplete duties {incomplete_duties}')

    if len(incomplete_duties) != 1:
        ask_which_roster_done(update)
        return
    
    # Update duty as completed
    duty = incomplete_duties[0]
    duty_id = duty['_id']
    Duties.update_one(
        { '_id': duty_id },
        { '$set': { 'isCompleted': True, 'isMissed': False } }
    )

    message = fr'✅ {user_text} just completed a chore\! 👏 👏 👏'

    # Find roster
    roster = Rosters.find_one(duty['roster_id'])
    if roster:
        roster_name = roster['name']
        message = fr'✅ {user_text} just completed *{roster_name}*\! 👏 👏 👏'

    logger.info('Reply message:\n' + message)
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
    logger.info('Edit message:\n' + message)
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)
    
    send_gif(query.message)

def send_gif(message: Message):
    url = get_gif()
    message.reply_animation(animation=url, quote=False)

def leave_roster(update: Update, _: CallbackContext):
    """Remove user from roster and remove duties"""
    user = update.effective_user

    query = update.callback_query
    query.answer()

    data = update.callback_query.data
    _, roster_id = data.split(".")
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)

    if roster is None:
        message = 'Oops! This chore has been removed.'
        logger.info('Edit message:\n' + message)
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
    message = f"{user_text} has left roster: *{roster_name}*"
    
    logger.info('Edit message:\n' + message)
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)
    
def leave_roster_select(update: Update, _: CallbackContext):
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

    if not rosters:
        message = fr'{user_text} you are not in any chore roster 🧐'
        logger.info('Reply message:\n' + message)
        update.message.reply_markdown_v2(message, quote=False)
        return

    message = fr'{user_text} which chore roster do you want to leave\?'
    keyboard = [roster_to_button(r, 'leave') for r in rosters]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)
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

    logger.info('Reply message:\n' + message)
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
        logger.info('Callback query message:\n' + message)
        update.callback_query.message.reply_markdown_v2(message, quote=False)
    # elif duty_date == today + datetime.timedelta(days=1):
    #     message = fr'📅 {user_text}: Your next *{roster_name}* duty is tomorrow'
    # else:
    #     date = duty['date'].strftime("%A %-d %b")
    #     message = fr'📅 {user_text}: Your next laundry duty is on {date}'

    # update.callback_query.message.reply_markdown_v2(message, quote=False)

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

def save_chat_group(update: Update, _: CallbackContext):
    user = update.effective_user
    user_id = user.id
    user_text = user.mention_markdown_v2()

    chat = update.effective_chat
    chat_id = chat.id
    chat_title = chat.title
    
    my_chat_member = update.my_chat_member
    # from_user = my_chat_member.from_user
    new_chat_member = my_chat_member.new_chat_member
    status = new_chat_member.status

    message = fr'Bot status\: `{status}` in {chat_title} by {user_text}'
    alert_creator(message)

    if status == constants.CHATMEMBER_MEMBER:
        chat_dict = get_chat_dict_from_chat(chat)
        chat_dict['addedBy'] = user_id
        # chat_dict['isWhitelisted'] = True
        Chats.update_one(
            { 'id': chat_dict['id'] },
            { '$set': chat_dict },
            upsert=True
        )
        time.sleep(1)
        send_intro(update)
    elif status in [constants.CHATMEMBER_KICKED, constants.CHATMEMBER_LEFT]:
        Chats.update_one(
            { 'id': chat_id },
            { '$set': { 'isRemoved': True } },
        )

    # create_user(user)

def send_intro(update: Update):
    logger.info('Sending self introduction')

    chat = update.effective_chat
    chat_id = chat.id

    message = INTRO_MESSAGE
    logger.info('Send message:\n' + message)

    bot = configure_telegram()
    bot.send_message(
        chat_id=chat_id,
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def delete_roster(update: Update, _: CallbackContext):
    """ Remove roster and duties """
    user = update.effective_user

    query = update.callback_query
    query.answer()

    data = update.callback_query.data
    _, roster_id = data.split(".")
    roster_id = ObjectId(roster_id)
    # roster = Rosters.find_one(roster_id)
    roster = Rosters.find_one_and_delete({
        '_id': roster_id
    })

    if roster is None:
        message = 'Oops! This chore has already been removed.'
        logger.info('Edit message:\n' + message)
        query.edit_message_text(text=message)
        return

    # Remove user duties
    delete_roster_duties(roster_id=roster_id)

    roster_name = roster['name']
    user_text = user.mention_markdown_v2()
    message = f"*{roster_name}* has been removed by {user_text}"
    
    logger.info('Edit message:\n' + message)
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)
    
def delete_roster_select(update: Update, _: CallbackContext):
    """ Let user select which roster to delete """
    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()
    # user_id = user.id

    # Get chat id
    chat_id = update.effective_chat.id

    rosters = Rosters.find(
        { 'chat_id': chat_id },
        projection={ 'name': True }
    )
    rosters = list(rosters)

    if not rosters:
        message = fr'There are no chore rosters 🧐'
        logger.info('Reply message:\n' + message)
        update.message.reply_markdown_v2(message, quote=False)
        return

    message = fr'{user_text} which chore roster do you want to delete\?'
    keyboard = [roster_to_button(r, 'deleteroster') for r in rosters]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )