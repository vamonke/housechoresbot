import random
import pymongo
import logging
import requests
import os
import json
import datetime
import pprint
from urllib.parse import urlencode

from queue import Queue
from threading import Thread

from telegram import (
    Update,
    Bot,
    # User,
    # InlineKeyboardMarkup,
    # InlineKeyboardButton,
    # constants
)

from telegram.ext import (
    # CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    Dispatcher,
    Filters,
    MessageHandler,
    Updater,
)

from commands_v2 import (
    start,
    show_duties,
    # create_duties,
    show_rosters,
    next_duty,
    mark_as_done,
    remind,
    get_chat_id,
    # reschedule,
    add_to_waitlist,
    create_roster,
    receive_roster_name,
    cancel,
    join_roster_select,
    join_roster,
    add_to_roster,
    mark_roster_as_done,
    show_rosters,
    leave_roster_select,
    leave_roster,
    send_beta_v2,
    whitelist_user,
    check_whitelist,
    GET_ROSTER_NAME,
)

from helpers import (
    get_whitelisted_chats,
    get_whitelisted_users
)

# Logging is cool!
logger = logging.getLogger()
if logger.handlers:
    for handler in logger.handlers:
        logger.removeHandler(handler)
logging.basicConfig(level=logging.INFO)

OK_RESPONSE = {
    'statusCode': 200,
    'headers': {'Content-Type': 'application/json'},
    'body': json.dumps('ok')
}
ERROR_RESPONSE = {
    'statusCode': 400,
    'body': json.dumps('Oops, something went wrong!')
}

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN') or '1783406286:AAElzXepih8u3OwKtvlvLYy3GC2eL8r1Ejk'
TEST_TELEGRAM_TOKEN = '1798724954:AAGuKOTuVWX8qfuRLUx1EU82Di9czAR6kFs'

ENVIRONMENT = os.environ.get('ENVIRONMENT')
IS_DEV = ENVIRONMENT is not 'prod'

user_properties = [
    'id',
    'first_name',
    'last_name',
    'username',
    'is_bot',
    'language_code',
]

WHITELISTED_USER_IDS = [
    # 265435469, # VAMONKE
    808439673,
    278239097,
    59546722,
]

def configure_telegram():
    """
    Configures the bot with a Telegram Token.
    Returns a bot instance.
    """
    TOKEN = TEST_TELEGRAM_TOKEN if IS_DEV else TELEGRAM_TOKEN
    if not TOKEN:
        logger.error('The TELEGRAM_TOKEN must be set')
        raise NotImplementedError

    print(TOKEN)
    return Bot(TOKEN)

def webhook(event, context):
    """
    Runs the Telegram webhook.
    """

    logger.info('Event: {}'.format(event))

    print(get_whitelisted_users())

    if event.get('httpMethod') == 'POST' and event.get('body'): 
        logger.info('Message received')
        
        # body = json.loads(event.get('body'))
        body = {'update_id': 136580210, 'message': {'message_id': 614, 'from': {'id': 265435469, 'is_bot': False, 'first_name': 'Varick', 'last_name': 'Lim', 'username': 'vamonke', 'language_code': 'en'}, 'chat': {'id': 265435469, 'first_name': 'Varick', 'last_name': 'Lim', 'username': 'vamonke', 'type': 'private'}, 'date': 1620406441, 'text': '/start', 'entities': [{'offset': 0, 'length': 6, 'type': 'bot_command'}]}}

        logger.info('Body: {}'.format(body))
        
        # Create bot and dispatcher instances
        bot = configure_telegram()
        dispatcher = Dispatcher(bot, None, workers=0)
        
        ##### Register handlers here #####
        dispatcher.add_handler(CommandHandler("start", check_whitelist(start)))
        
        update = Update.de_json(body, bot)
        dispatcher.process_update(update)

def set_webhook(event, context):
    """
    Sets the Telegram bot webhook.
    `curl -X POST https://9mxwam4oc4.execute-api.ap-southeast-1.amazonaws.com/dev/set_webhook`
    """

    logger.info('Event: {}'.format(event))
    bot = configure_telegram()
    url = 'https://{}/{}/'.format(
        event.get('headers').get('Host'),
        event.get('requestContext').get('stage'),
    )
    webhook = bot.set_webhook(url)

    if webhook:
        return OK_RESPONSE

    return ERROR_RESPONSE

def main():
    TOKEN = TEST_TELEGRAM_TOKEN if IS_DEV else TELEGRAM_TOKEN
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", check_whitelist(start)))
    dispatcher.add_handler(CommandHandler("done", check_whitelist(mark_as_done)))
    dispatcher.add_handler(CommandHandler("duties", check_whitelist(show_duties)))
    dispatcher.add_handler(CommandHandler("join", check_whitelist(join_roster_select)))
    dispatcher.add_handler(CommandHandler("rosters", check_whitelist(show_rosters)))
    dispatcher.add_handler(CommandHandler("leave", check_whitelist(leave_roster_select)))
    # dispatcher.add_handler(CommandHandler("reschedule", check_whitelist(reschedule)))
    # dispatcher.add_handler(CommandHandler("editduty", check_whitelist(editduty)))
    # dispatcher.add_handler(CommandHandler("nextduty", check_whitelist(next_duty)))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('createroster', check_whitelist(create_roster))],
        states={
            GET_ROSTER_NAME: [MessageHandler(Filters.text & ~Filters.command, receive_roster_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    dispatcher.add_handler(conv_handler)

    dispatcher.add_handler(CallbackQueryHandler(join_roster, pattern='^(joinnewroster|join)\.'))
    dispatcher.add_handler(CallbackQueryHandler(add_to_roster, pattern='^addtoroster\.'))
    dispatcher.add_handler(CallbackQueryHandler(mark_roster_as_done, pattern='^rosterdone\.'))
    dispatcher.add_handler(CallbackQueryHandler(leave_roster, pattern='^leave\.'))

    dispatcher.add_handler(CommandHandler("welcome", whitelist_user))
    # dispatcher.add_handler(MessageHandler(blacklisted_filter, send_beta_v2))    

    updater.start_polling()
    updater.idle()

def main_dev():
    body = {'update_id': 136580210, 'message': {'message_id': 614, 'from': {'id': 265435469, 'is_bot': False, 'first_name': 'Varick', 'last_name': 'Lim', 'username': 'vamonke', 'language_code': 'en'}, 'chat': {'id': 265435469, 'first_name': 'Varick', 'last_name': 'Lim', 'username': 'vamonke', 'type': 'private'}, 'date': 1620406441, 'text': '/start', 'entities': [{'offset': 0, 'length': 6, 'type': 'bot_command'}]}}

    # Create bot, update queue and dispatcher instances
    bot = configure_telegram()
    dispatcher = Dispatcher(bot, None, workers=0)
    
    ##### Register handlers here #####
    dispatcher.add_handler(CommandHandler("start", check_whitelist(start)))
    
    update = Update.de_json(body, bot)
    dispatcher.process_update(update)

# if __name__ == '__main__':
#     if IS_DEV:
        # main()
        # main_dev()
        # routine(None, None)