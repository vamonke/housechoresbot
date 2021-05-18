import datetime
from bson.objectid import ObjectId

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

# from commands_v2 import (
#     roster_to_button,
# )

from helpers import (
    duty_to_button,
    find_incomplete_duties,
    send_chore_missing_message,
    cancel_button,
)

from logger import logger

def delete_command(update: Update, _: CallbackContext):
    """
        /delete: Ask which duties to delete
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

    message = fr'{user_text} which chore do you want to delete\?'
    keyboard = [duty_to_button(d, 'deleteduty') for d in incomplete_duties]
    keyboard.append(cancel_button)
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        reply_markup=reply_markup,
        quote=False,
    )

def delete_duty_callback(update: Update, _: CallbackContext):
    """
        /delete -> [duty]
        Check if duty is weekly. If yes, ask user if they want to delete recurring duties.
        Receive: duty_id
        Reply: Message or Yes/No
    """
    # Answer query
    query = update.callback_query
    query.answer()

    # Get user
    user = update.effective_user
    user_id = user.id

    # Find duty
    data = update.callback_query.data
    _, duty_id = data.split(".")
    duty_id = ObjectId(duty_id)
    duty = Duties.find_one(duty_id)
    duty_date = duty["date"]
    duty_day = duty_date.weekday()

    # Find roster
    roster_id = duty["roster_id"]
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)
    roster_schedule = roster["schedule"]
    duty["name"] = roster["name"]

    is_weekly_duty = any(
        (us['dutyDay'] == duty_day and us['id'] == user_id)
        for us in roster_schedule
    )

    logger.info(fr'Selected duty {duty_id} is_weekly_duty: {is_weekly_duty}')
    if is_weekly_duty:
        return check_delete_weekly_duty(update, duty)
    else:
        return delete_single_duty(update, duty)

def delete_single_duty(update: Update, duty: dict):
    """
        /delete -> [duty]
        Delete single duty
        Receive: duty_id
        Reply: Message
    """
    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    # Delete duty
    Duties.find_one_and_delete({ '_id': duty['_id'] })

    duty_date = duty['date']
    duty_date_str = duty_date.strftime("%a %d %b")
    roster_name = duty["name"]

    message = fr"Chore removed for {user_text}: *{roster_name}* on *{duty_date_str}*"
    
    logger.info('Edit message:\n' + message)
    update.callback_query.edit_message_text(
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def check_delete_weekly_duty(update: Update, duty: dict):
    """
        /delete -> [duty]
        Check if duty is weekly. If yes, ask user if they want to delete recurring duties.
        Receive: duty_id
        Reply: Message or Yes/No
    """
    # Get user
    user = update.effective_user
    user_text = user.mention_markdown_v2()

    duty_id = duty['_id']
    duty_date = duty['date']
    duty_date_str = duty_date.strftime("%a %d %b")
    # duty_day_str = duty_date.strftime("%a")
    roster_name = duty["name"]

    message = fr'Delete chore: *{roster_name}* on *{duty_date_str}*' + '\n'
    message += fr'{user_text} this is a weekly chore\. '
    message += fr'Do you want to delete future chores too?'

    button_text_single = fr'Delete this chore only'
    button_text_repeat = fr'Delete this and future chores'
    callback_data_single = fr'deletedutysingle.{duty_id}'
    callback_data_repeat = fr'deletedutyweekly.{duty_id}'

    keyboard = [
        [InlineKeyboardButton(button_text_single, callback_data=callback_data_single)],
        [InlineKeyboardButton(button_text_repeat, callback_data=callback_data_repeat)],
    ]
    keyboard.append(cancel_button)
    reply_markup = InlineKeyboardMarkup(keyboard)

    logger.info('Edit message:\n' + message)
    update.callback_query.edit_message_text(
        text=message,
        reply_markup=reply_markup,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def delete_duty_single_callback(update: Update, _: CallbackContext):
    """
        /delete -> [duty] -> [Delete this chore only]
        Delete selected duty without removing from roster
        Receive: duty_id
        Reply: Message
    """
    query = update.callback_query
    query.answer()
    
    # Find duty
    data = update.callback_query.data
    _, duty_id = data.split(".")
    duty_id = ObjectId(duty_id)
    duty = Duties.find_one(duty_id)

    # Find roster
    roster_id = duty["roster_id"]
    roster_id = ObjectId(roster_id)
    roster = Rosters.find_one(roster_id)
    duty["name"] = roster["name"]

    delete_single_duty(
        update=update,
        duty=duty,
    )

def delete_duty_weekly_callback(update: Update, _: CallbackContext):
    """
        /delete -> [duty] -> [Delete this and future chores]
        Delete selected duty and remove from roster
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
    
    # Find duty
    data = update.callback_query.data
    _, duty_id = data.split(".")
    duty_id = ObjectId(duty_id)
    duty = Duties.find_one(duty_id)
    if duty is None:
        return send_chore_missing_message(update)

    # Find roster
    roster_id = duty["roster_id"]
    roster_id = ObjectId(roster_id)

    # Remove user duties
    duty_date = duty['date']
    delete_weekly_duty(
        roster_id=roster_id,
        user_id=user_id,
        from_date=duty_date,
    )

    roster = Rosters.find_one(roster_id)
    if roster:
        remove_from_roster(
            roster=roster,
            user_id=user_id,
            duty_day=duty_date.weekday()
        )
    else:
        logger.warn(fr"Missing roster {roster_id}")

    roster_name = roster['name']
    duty_day_str = duty_date.strftime("%A")
    message = fr"Chore removed for {user_text}: *{roster_name}* on *{duty_day_str}s*"
    # message = f"*{roster_name}* has been removed by {user_text}"
    
    logger.info('Edit message:\n' + message)
    query.edit_message_text(text=message, parse_mode=constants.PARSEMODE_MARKDOWN_V2)

def delete_weekly_duty(roster_id: ObjectId, user_id: int, from_date):
    """ Remove future user duties from this roster """
    logger.info(fr'Removing duties with user_id {user_id} and roster_id {roster_id} from {from_date} onwards')
    result = Duties.delete_many(
        {
            'user': user_id,
            'roster_id': roster_id,
            'isCompleted': False,
            'date': { '$gte': from_date },
        }
    )
    logger.info('Bulk delete duties result:')
    logger.info(result.raw_result)

def remove_from_roster(roster: dict, user_id: int, duty_day: int):
    """ Remove existing user + day from roster schedule """
    result = Rosters.update_one(
        { '_id': roster["_id"] },
        { '$pull':
            { 'schedule':
                {
                    'id': user_id,
                    'dutyDay': duty_day
                }
            }
        },
    )
    logger.info('Update roster result:')
    logger.info(result.raw_result)