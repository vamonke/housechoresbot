import datetime
import os
import sys

if "TELEGRAM_TOKEN" not in os.environ:
    arg_token = sys.argv[1]
    os.environ["TELEGRAM_TOKEN"] = arg_token # TELEGRAM_TOKEN
    print("TELEGRAM_TOKEN: " + os.environ["TELEGRAM_TOKEN"])

if "MONGODB_URI" not in os.environ:
    arg_uri = sys.argv[2]
    os.environ["MONGODB_URI"] = arg_uri # MONGODB_URI
    print('MONGODB_URI: ' + os.environ["MONGODB_URI"])

from telegram import (
    Bot,
    Update,
    User,
    constants
)

from mongo import (
    Chats,
    Rosters,
    Duties,
    Users,
)

from helpers import (
    configure_telegram,
)

from logger import logger

def remind(event, context):
    """
      1. Sends reminder (if any)
      `serverless invoke local --function remind`
    """
    name = context.function_name
    current_time = datetime.datetime.now().time()
    logger.info("Function " + name + " ran at " + str(current_time))

    bot = configure_telegram()
    send_reminder(bot)

def send_reminder(bot: Bot):
    """ Send reminder for all chats """
    # Find all chats
    # chats = Chats.find({ 'id': { '$in': [-463862443] } }) # FOR TESTING
    chats = Chats.find()

    # Send reminder for each chat
    for chat in chats:
        send_reminder_to_chat(bot, chat)


def send_reminder_to_chat(bot: Bot, chat: dict):
    """ Send reminder message to chat """
    chat_id = chat['id']

    # Remind today's duties
    message = get_remind_message(chat_id)
    if message:
        bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=constants.PARSEMODE_MARKDOWN_V2
        )
        logger.info(fr'Message sent to {chat_id}: {message}')

def get_remind_message(chat_id: int):
    """ Get reminder message """
    # Get reminder window
    now = datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)

    # Find today's uncompleted duties
    today_duties = Duties.find(
        {
            'chat_id': chat_id,
            'isCompleted': False,
            'date': today
        },
        projection={ 'name': True, 'user': True, 'roster_id': True, 'date': True },
        sort=[('date', 1)]
    )
    today_duties = list(today_duties)
    
    if not today_duties:
        return ''

    # Get rosters
    rosters = Rosters.find({ 'chat_id': chat_id }, projection={ 'name': True })
    rosters = list(rosters)
    rosters_dict = {r['_id']: r['name'] for r in rosters}
    # rosters_dict

    # Get users
    user_ids = [d['user'] for d in today_duties]
    users = Users.find({ 'id': { '$in': user_ids } })
    users = list(users)
    users_dict = {u['id']: User(**u).mention_markdown_v2() for u in users}
    # users_dict
    
    # Craft message
    message = "📣 We have some chores for today\!\n"
    for d in today_duties:
        roster_name = rosters_dict[d['roster_id']]
        user_text = users_dict[d['user']]
        duty_line = fr"\- {roster_name}: {user_text}" + "\n"
        message += duty_line

    message += "\nSend \/done once you\'ve completed your chore 👌"

    return message

if __name__ == '__main__':
    class context:
        function_name = 'remind'

    remind(None, context())