import datetime
from bson.objectid import ObjectId

from telegram import (
    Update,
    InlineKeyboardMarkup,
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
    roster_to_button,
)

from helpers import (
    send_gif,
    duty_to_button,
)

from logger import logger

def done_command(update: Update, _: CallbackContext):
    """
        /done
        Find incomplete duties
        - If only 1 found, mark it as done
        - If multiple found, ask user select duty
        - If none found, ask user select roster
    """
    # Get chat id
    chat_id = update.effective_chat.id

    # Get user
    user = update.effective_user
    user_id = user.id

    # Get date window
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    # window_start = today - datetime.timedelta(days=2)
    # window_end = today + datetime.timedelta(days=1)
    window_start = today - datetime.timedelta(days=today.weekday())
    window_end = today + datetime.timedelta(days=6)

    # Find uncompleted duties in date window
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

def ask_which_duty_done(update: Update, incomplete_duties):
    """
        /done: Multiple incomplete duties found
        Ask user to select which duty to mark as done
        Receive: None
        Reply: [duties]
    """

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

def mark_duty_as_done_callback(update: Update, _: CallbackContext):
    """
        /done -> [duty]
        Mark selected duty as done
        Receive: duty_id
        Reply: GIF
    """
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

def ask_which_roster_done(update: Update):
    """
        /done: No incomplete duties found
        Get rosters and ask user to select which roster to add done duty
        Receive: None
        Reply: [Rosters]
    """

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
    """
        /done -> [roster]
        Add new duty with selected roster and mark it as done
        Receive: roster_id
        Reply: GIF
    """
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

    # Get date
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)

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

    message = fr'✅ {user_text} just completed *{roster_name}*\! 👏 👏 👏'

    logger.info('Edit message:\n' + message)
    query.edit_message_text(
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2
    )
    
    send_gif(query.message)

def mark_duty_as_done(update: Update, duty: dict, roster: dict = None):
    """
        Function to mark duty as done
        Receive: duty, roster
        Reply: GIF
    """
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