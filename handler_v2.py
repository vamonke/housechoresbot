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
    ChatMemberHandler,
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
    add_to_new_roster,
    add_to_roster,
    mark_roster_as_done,
    show_rosters,
    leave_roster_select,
    leave_roster,
    send_beta_v2,
    whitelist_user,
    check_whitelist,
    save_chat_group,
    GET_ROSTER_NAME,
)

from helpers import (
    configure_telegram,
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

TELEGRAM_TOKEN = '1783406286:AAElzXepih8u3OwKtvlvLYy3GC2eL8r1Ejk'
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

def webhook(event, context):
    """
    Runs the Telegram webhook.
    """

    logger.info('Event: {}'.format(event))

    if event.get('httpMethod') == 'POST' and event.get('body'): 
        logger.info('Message received')

        # Get event body
        body = json.loads(event.get('body'))
        logger.info('Body: {}'.format(body))
        
        # Create bot and dispatcher instances
        bot = configure_telegram()
        dispatcher = Dispatcher(bot, None, workers=0)
        add_handlers(dispatcher)
        
        update = Update.de_json(body, bot)
        dispatcher.process_update(update)

        return OK_RESPONSE

    return ERROR_RESPONSE

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

def add_handlers(dispatcher):
    # Commands
    dispatcher.add_handler(CommandHandler("start", check_whitelist(start)))
    dispatcher.add_handler(CommandHandler("createroster", check_whitelist(create_roster)))
    dispatcher.add_handler(MessageHandler(Filters.reply & ~Filters.command, check_whitelist(receive_roster_name)))
    dispatcher.add_handler(CommandHandler("done", check_whitelist(mark_as_done)))
    dispatcher.add_handler(CommandHandler("duties", check_whitelist(show_duties)))
    dispatcher.add_handler(CommandHandler("join", check_whitelist(join_roster_select)))
    dispatcher.add_handler(CommandHandler("rosters", check_whitelist(show_rosters)))
    dispatcher.add_handler(CommandHandler("leave", check_whitelist(leave_roster_select)))
    # dispatcher.add_handler(CommandHandler("reschedule", check_whitelist(reschedule)))
    # dispatcher.add_handler(CommandHandler("editduty", check_whitelist(editduty)))
    # dispatcher.add_handler(CommandHandler("nextduty", check_whitelist(next_duty)))

    # Create roster conversation
    # conv_handler = ConversationHandler(
    #     entry_points=[CommandHandler('createroster', check_whitelist(create_roster))],
    #     states={
    #         GET_ROSTER_NAME: [MessageHandler(Filters.text & ~Filters.command, receive_roster_name)],
    #     },
    #     fallbacks=[CommandHandler('cancel', cancel)],
    # )
    # dispatcher.add_handler(conv_handler)

    # Callback handlers
    dispatcher.add_handler(CallbackQueryHandler(join_roster, pattern='^(joinnewroster|join)\.'))
    dispatcher.add_handler(CallbackQueryHandler(add_to_new_roster, pattern='^addtonewroster\.'))
    dispatcher.add_handler(CallbackQueryHandler(add_to_roster, pattern='^addtoroster\.'))
    dispatcher.add_handler(CallbackQueryHandler(mark_roster_as_done, pattern='^rosterdone\.'))
    dispatcher.add_handler(CallbackQueryHandler(leave_roster, pattern='^leave\.'))

    # Beta message
    dispatcher.add_handler(CommandHandler("welcome", whitelist_user))
    # dispatcher.add_handler(MessageHandler(blacklisted_filter, send_beta_v2))
    dispatcher.add_handler(ChatMemberHandler(save_chat_group))

def main():
    updater = Updater(TELEGRAM_TOKEN)
    # updater = Updater(TEST_TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    add_handlers(dispatcher)
    updater.start_polling()
    updater.idle()

def dev():
    body = {'update_id': 136580227, 'my_chat_member': {'chat': {'id': -463862443, 'type': 'group', 'title': 'CHATBOT TEST', 'all_members_are_administrators': True}, 'date': 1620411340, 'old_chat_member': {'user': {'id': 1798724954, 'first_name': 'Duty Roster Bot', 'is_bot': True, 'username': 'DutyRosterBot'}, 'status': 'member', 'until_date': None}, 'new_chat_member': {'user': {'id': 1798724954, 'first_name': 'Duty Roster Bot', 'is_bot': True, 'username': 'DutyRosterBot'}, 'status': 'left', 'until_date': None}, 'from': {'id': 265435469, 'first_name': 'Varick', 'is_bot': False, 'last_name': 'Lim', 'username': 'vamonke', 'language_code': 'en'}}}
    
    # Create bot and dispatcher instances
    bot = configure_telegram()
    dispatcher = Dispatcher(bot, None, workers=0)
    add_handlers(dispatcher)

    update = Update.de_json(body, bot)
    dispatcher.process_update(update)

if __name__ == '__main__':
    main()
    # dev()
    # routine(None, None)