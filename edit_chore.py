import datetime
from bson.objectid import ObjectId
import pymongo

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
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
    create_user_duties,
)

from delete_chore import (
    delete_weekly_duty,
)

from helpers import (
    duty_to_button,
    find_incomplete_duties,
    send_chore_missing_message,
    cancel_button,
    add_name_to_duty,
    date_to_button,
    is_duty_weekly,
    get_user_dict_from_user,
)

from logger import logger

def edit_command(update: Update, _: CallbackContext):
    """
        /edit: Ask which duties to edit
        Ask user to select which duty to mark as done
        Receive: None
        Reply: [duties]
    """
    # Get user
    user = update.effective_user
    user_id = user.id
    user_text = user.mention_markdown_v2()

    # Get chat
    chat = update.effective_chat
    chat_id = chat.id

    # Find incomplete duties
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    from_date = today - datetime.timedelta(days=today.weekday())
    to_date = today + datetime.timedelta(days=6)
    incomplete_duties = find_incomplete_duties(chat_id, user_id, from_date, to_date)

    if not incomplete_duties:
        message = "🧐 No chores found this week"
        update.message.reply_markdown_v2(message, quote=False)
        return

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

    message = fr'{user_text} which chore do you want to edit\?'
    keyboard = [duty_to_button(d, 'editduty') for d in incomplete_duties]
    keyboard.append(cancel_button)
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )

def edit_duty_callback(update: Update, _: CallbackContext):
    """
        /edit -> [duty]
        Ask user whether to change date or change person
        Receive: duty_id
        Reply: [Change person][Change duty]
    """
    query = update.callback_query
    query.answer()

    user = update.effective_user
    user_id = user.id
    user_text = user.mention_markdown_v2()
    
    # Get duty
    data = update.callback_query.data
    _, duty_id = data.split(".")
    duty_id = ObjectId(duty_id)
    duty = Duties.find_one(duty_id)

    if duty is None:
        return send_chore_missing_message(update)
    if duty['user'] != user_id:
        return logger.info('User id mismatch. Ignoring..')

    duty = add_name_to_duty(duty)

    roster_name = duty['name']
    duty_date_str = duty['date'].strftime("%a %d %b")

    message = fr'Edit chore: *{roster_name}* on *{duty_date_str}* by {user_text}'

    callback_data_one = f'rescheduleduty.{duty_id}'
    # callback_data_repeat = f'reassign.{duty_id}'

    keyboard = [
        # [InlineKeyboardButton("👤 Change person", callback_data=callback_data_repeat)],
        [InlineKeyboardButton("📅 Change date", callback_data=callback_data_one)],
        cancel_button,
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Edit message:\n' + message)
    query.edit_message_text(
        text=message,
        reply_markup=reply_markup,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def reschedule_duty_callback(update: Update, _: CallbackContext):
    """
        /edit -> [duty] -> [Change date]
        Let use choose new date for duty
        Receive: duty_id
        Reply: dates
    """
    # Answer query
    query = update.callback_query
    query.answer()

    # Get user
    user = update.effective_user
    user_id = user.id
    user_text = user.mention_markdown_v2()

    # Get duty
    data = update.callback_query.data
    _, duty_id = data.split(".")
    duty_id = ObjectId(duty_id)
    duty = Duties.find_one(duty_id)

    if duty is None:
        return send_chore_missing_message(update)
    if duty['user'] != user_id:
        return logger.info('User id mismatch. Ignoring..')

    duty = add_name_to_duty(duty)

    # Reply message
    roster_name = duty['name']
    duty_date = duty['date']
    duty_date_str = duty_date.strftime("%a %d %b")
    message = fr'Change date: *{roster_name}* on *{duty_date_str}*' + '\n'
    message += fr'{user_text} pick a new date:'

    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    
    # Reply markup
    date_list = [today + datetime.timedelta(days=x) for x in range(6)]
    date_list = [d for d in date_list if d != duty_date]

    callback_text = fr"rescheduledutydate.{duty_id}"
    keyboard = [date_to_button(date, callback_text) for date in date_list]
    keyboard.append(cancel_button)
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Edit message:\n' + message)
    query.edit_message_text(
        text=message,
        reply_markup=reply_markup,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def reschedule_duty_date_callback(update: Update, _: CallbackContext):
    """
        /edit -> [duty] -> [Change date] -> [date]
        Check if duty is weekly
        Receive: duty_id, date
        Reply: message
    """
    # Answer query
    query = update.callback_query
    query.answer()

    # Get user
    user = update.effective_user
    user_id = user.id

    # Parse input data
    data = update.callback_query.data
    _, duty_id, new_date = data.split(".")
    new_date = datetime.datetime.strptime(new_date, "%x")
    duty_id = ObjectId(duty_id)

    # Find duty
    duty = Duties.find_one(duty_id)
    if duty is None:
        return send_chore_missing_message(update)
    if duty['user'] != user_id:
        return logger.info('Unauthorised. User id mismatch. Ignoring..')

    # Find roster
    roster_id = duty["roster_id"]
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)
    duty["name"] = roster["name"]

    is_weekly_duty = is_duty_weekly(duty, roster)
    logger.info(fr'Selected duty {duty_id} is_weekly_duty: {is_weekly_duty}')
    if is_weekly_duty:
        return check_reschedule_weekly_duty(update, duty, new_date)
    else:
        return reschedule_single_duty(update, duty, new_date)
    
def reschedule_single_duty(update: Update, duty: dict, new_date: datetime.datetime):
    """
        /edit -> [duty] -> [Change date] -> [date]
        Reschedule single duty
        Receive: duty_id
        Reply: Message
    """
    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    now = datetime.datetime.now()

    # Update duty
    Duties.find_one_and_update(
        { '_id': duty['_id'] },
        { '$set':
            {
                'date': new_date,
                'modifiedAt': now,
            }
        }
    )

    old_date = duty['date']
    old_date_str = old_date.strftime("%a %d %b")
    new_date_str = new_date.strftime("%a %d %b")
    roster_name = duty["name"]

    message = fr"📅 {user_text} changed date for *{roster_name}* from *{old_date_str}* to *{new_date_str}*"
    
    logger.info('Edit message:\n' + message)
    update.callback_query.edit_message_text(
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def check_reschedule_weekly_duty(update: Update, duty: dict, new_date: datetime.datetime):
    """
        /edit -> [duty] -> [Change date] -> [date]
        Ask user if they want to reschedule recurring duties
        Receive: duty_id
        Reply: Message or Yes/No
    """
    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    duty_id = duty['_id']
    roster_name = duty["name"]
    old_date = duty['date']
    old_date_str = old_date.strftime("%a %d %b")
    new_date_str = new_date.strftime("%a %d %b")

    message = fr'Edit chore: *{roster_name}* from *{old_date_str}* to *{new_date_str}*' + '\n'
    message += fr'{user_text} this is a weekly chore\. '
    message += fr'Do you want to change dates for future chores too?'

    new_date_data = new_date.strftime("%x")

    button_text_single = fr'Edit this chore only'
    button_text_repeat = fr'Edit this and future chores'
    callback_data_single = fr'rescheduledutysingle.{duty_id}.{new_date_data}'
    callback_data_repeat = fr'rescheduledutyweekly.{duty_id}.{new_date_data}'

    keyboard = [
        [InlineKeyboardButton(button_text_single, callback_data=callback_data_single)],
        [InlineKeyboardButton(button_text_repeat, callback_data=callback_data_repeat)],
        cancel_button,
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Edit message:\n' + message)
    update.callback_query.edit_message_text(
        text=message,
        reply_markup=reply_markup,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def reschedule_duty_single_callback(update: Update, _: CallbackContext):
    """
        /reschedule -> [duty] -> [reschedule this chore only]
        reschedule selected duty without removing from roster
        Receive: duty_id
        Reply: Message
    """
    query = update.callback_query
    query.answer()
    
    # Get user
    user = update.effective_user
    user_id = user.id

    # Parse input data
    data = update.callback_query.data
    _, duty_id, new_date = data.split(".")
    new_date = datetime.datetime.strptime(new_date, "%x")
    duty_id = ObjectId(duty_id)

    # Find duty
    duty = Duties.find_one(duty_id)
    if duty is None:
        return send_chore_missing_message(update)
    if duty['user'] != user_id:
        return logger.info('Unauthorised. User id mismatch. Ignoring..')

    duty = add_name_to_duty(duty)
    reschedule_single_duty(
        update=update,
        duty=duty,
        new_date=new_date,
    )


def reschedule_duty_weekly_callback(update: Update, _: CallbackContext):
    """
        /reschedule -> [duty] -> [reschedule this and future chores]
        reschedule duties and remove from roster schedule
        Receive: duty_id
        Reply: Message
    """
    # Answer query
    query = update.callback_query
    query.answer()

    # Get user
    user = update.effective_user
    user_id = user.id
    user_text = user.mention_markdown_v2()
    
    # Parse input data
    data = update.callback_query.data
    _, duty_id, new_date = data.split(".")
    new_date = datetime.datetime.strptime(new_date, "%x")
    duty_id = ObjectId(duty_id)

    # Find duty
    duty = Duties.find_one(duty_id)
    if duty is None:
        return send_chore_missing_message(update)
    if duty['user'] != user_id:
        return logger.info('User id mismatch. Ignoring..')

    # Delete matching duties
    roster_id = duty["roster_id"]
    roster_id = ObjectId(roster_id)
    old_date = duty['date']
    delete_weekly_duty(roster_id, user_id, old_date)
    
    # Get duty days
    old_duty_day = old_date.weekday()
    new_duty_day = new_date.weekday()

    # Edit user in roster schedule
    roster = edit_roster_user(roster_id, user_id, old_duty_day, new_duty_day)

    # Create new user duties
    user_dict = get_user_dict_from_user(user)
    user_dict['dutyDay'] = new_duty_day
    create_user_duties(
        user_dict=user_dict,
        roster=roster,
        update=update,
    )

    roster_name = roster['name']
    old_day_str = old_date.strftime("%A")
    new_day_str = new_date.strftime("%A")
    message = fr"📅 {user_text} changed date for *{roster_name}* from *{old_day_str}* to *{new_day_str}*"
    
    logger.info('Edit message:\n' + message)
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)

def edit_roster_user(roster_id, user_id, old_duty_day, new_duty_day) -> dict:
    roster = Rosters.find_one_and_update(
        { '_id': roster_id },
        {
            '$set': {
                'schedule.$[user].dutyDay': new_duty_day
            },
        },
        array_filters=[{ 'user.id': user_id,  "user.dutyDay": old_duty_day }],
        return_document=pymongo.ReturnDocument.AFTER,
    )
    return roster