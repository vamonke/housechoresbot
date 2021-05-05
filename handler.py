import random
import pymongo
import logging
import requests
import os
import json
import datetime
import pprint
from urllib.parse import urlencode

from telegram import (
    Update,
    Bot,
    User,
    InlineKeyboardMarkup,
    # InlineKeyboardButton,
    constants
)

from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    CallbackContext,
    ConversationHandler,
    Filters,
)

from commands_v2 import (
    start,
    join,
    # leave,
    show_duties,
    # create_duties,
    # create_schedule,
    show_schedule,
    next_duty,
    mark_as_done,
    # callback_handler,
    remind,
    get_chat_id,
    # reschedule,
    add_to_waitlist,
    create_roster,
    receive_roster_name,
    join_roster,
    add_to_roster,
    cancel,
    GET_ROSTER_NAME,
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

# TELEGRAM_TOKEN = '1783406286:AAElzXepih8u3OwKtvlvLYy3GC2eL8r1Ejk'
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

LIM_FAMILY_USER_IDS = [
    # 265435469, # VAMONKE
    808439673,
    278239097,
    59546722,
]

VAMONKE_ID = 265435469

HOUSE_CHORES_BOT_USERNAME = 'HouseChoresBot'
HOUSE_CHORES_BOT_ID = 1783406286

def configure_telegram():
    """
    Configures the bot with a Telegram Token.
    Returns a bot instance.
    """

    TELEGRAM_TOKEN = TEST_TELEGRAM_TOKEN if is_dev else os.environ.get('TELEGRAM_TOKEN')
    if not TELEGRAM_TOKEN:
        logger.error('The TELEGRAM_TOKEN must be set')
        raise NotImplementedError

    return Bot(TELEGRAM_TOKEN)

def send_beta(update):
    message = add_to_waitlist(update)
    if update.message is not None and message is not None:
        update.message.reply_markdown_v2(message, quote=False)
        logger.info(message)

    message = fr"Someone spoke to HouseChoresBot\! ❓"
    if update.effective_user is not None:
        user_text = update.effective_user.mention_markdown_v2()
        message = fr"{user_text} spoke to HouseChoresBot\! 😀"

    alert_creator(message)

def handle_kick(update):
    user_text = update.effective_user.mention_markdown_v2()
    chat_title = update.effective_chat.title
    message = fr"{user_text} kicked HouseChoresBot from {chat_title}\! 🥺"
    alert_creator(message)

def handle_add(update):
    user_text = update.effective_user.mention_markdown_v2()
    chat_title = update.effective_chat.title
    message = fr"{user_text} added HouseChoresBot to {chat_title}\! 😀"
    alert_creator(message)

def alert_creator(message):
    bot = configure_telegram()
    bot.send_message(
        chat_id=VAMONKE_ID,
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
    )

def get_is_kicked(update):
    return (
        update.message is not None and \
        update.message.left_chat_member is not None and \
        update.message.left_chat_member.id == HOUSE_CHORES_BOT_ID
    ) or (
        update.my_chat_member is not None and \
        update.my_chat_member.old_chat_member is not None and \
        update.my_chat_member.old_chat_member.user.id == HOUSE_CHORES_BOT_ID
    ) or (
        update.my_chat_member is not None and \
        update.my_chat_member.new_chat_member is not None and \
        update.my_chat_member.new_chat_member.user.id == HOUSE_CHORES_BOT_ID and \
        update.my_chat_member.new_chat_member.status == 'kicked'
    )

def get_is_added(update):
    return (
        update.message is not None and \
        update.message.new_chat_members is not None and \
        any(ncm.id == HOUSE_CHORES_BOT_ID for ncm in update.message.new_chat_members)
    )

def webhook(event, context):
    """
    Runs the Telegram webhook.
    """

    bot = configure_telegram()
    logger.info('Event: {}'.format(event))

    if event.get('httpMethod') == 'POST' and event.get('body'): 
        logger.info('Message received')
        
        body = json.loads(event.get('body'))
        logger.info('Body: {}'.format(body))
        update = Update.de_json(body, bot)

        # logger.info('Update: {}'.format(update))
        # logger.info('Message: {}'.format(update.message))
        # logger.info('left_chat_member: {}'.format(update.message.left_chat_member))
        # logger.info('left_chat_member.id: {}'.format(update.message.left_chat_member.id))
        # logger.info('left_chat_member.id: {}'.format(update.message.left_chat_member.id))

        # Check if bot is added
        is_added = get_is_added(update)
        logger.info('is_added: {}'.format(is_added))
        if is_added:
            handle_add(update)
            return OK_RESPONSE

        # Check if bot is kicked
        is_kicked = get_is_kicked(update)
        logger.info('is_kicked: {}'.format(is_kicked))
        if is_kicked:
            handle_kick(update)
            return OK_RESPONSE

        if update.callback_query is None and update.message is None:
            logger.warn('No callback_query or message')
            return OK_RESPONSE

        # Check for whitelisted IDs
        if update.effective_user is None or update.effective_user.id not in LIM_FAMILY_USER_IDS:
            send_beta(update)
            return OK_RESPONSE

        reply_markup = None
        message = None

        if update.callback_query and update.callback_query.message:
            chat_id = update.callback_query.message.chat.id
            message = callback_handler(update)
        else:
            chat_id = update.message.chat.id
            text = update.message.text

            if text == '/start':
                message = start(update)
            elif text == '/join':
                message, reply_markup = join(update)
            # elif text == '/leave':
            #     message = leave(update)
            elif text == '/duties':
                message = show_duties(update)
            # elif text == '/createduties':
            #     message = create_duties()
            # elif text == '/createschedule':
            #     message = create_schedule(update)
            elif text == '/schedule':
                message = show_schedule(update)
            elif text == '/reschedule':
                message, reply_markup = reschedule(update)
            elif text == '/nextduty':
                message = next_duty(update)
            elif text == '/done':
                message = mark_as_done(update)

        if message is not None:
            bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode=constants.PARSEMODE_MARKDOWN_V2,
            )
            logger.info('Message sent')

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

def routine(event, context):
    """
      1. Sends reminder (if any)
      2. Creates upcoming duties
      `serverless invoke local --function routine`
    """

    current_time = datetime.datetime.now().time()
    name = context.function_name
    logger.info("Cron function " + name + " ran at " + str(current_time))
    
    bot = configure_telegram()
    chat_id = get_chat_id()

    message = remind()
    if message is not None:
        bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=constants.PARSEMODE_MARKDOWN_V2
        )
        logger.info(fr'Message sent: {message}')

    create_duties()

def main():
    updater = Updater(TEST_TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    # dispatcher.add_handler(CommandHandler("done", lambda update, _ : function_wrapper(mark_as_done, update)))
    dispatcher.add_handler(CommandHandler("duties", show_duties))
    # dispatcher.add_handler(CommandHandler("schedule", lambda update, _ : function_wrapper(show_schedule, update)))
    # dispatcher.add_handler(CommandHandler("reschedule", lambda update, _ : function_wrapper(reschedule, update)))
    # dispatcher.add_handler(CommandHandler("join", lambda update, _ : function_wrapper(join, update)))
    # dispatcher.add_handler(CommandHandler("leave", lambda update, _ : function_wrapper(leave, update)))
    # dispatcher.add_handler(CommandHandler("nextduty", lambda update, _ : function_wrapper(next_duty, update)))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('createroster', create_roster)],
        states={
            GET_ROSTER_NAME: [MessageHandler(Filters.text & ~Filters.command, receive_roster_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    dispatcher.add_handler(conv_handler)

    updater.dispatcher.add_handler(CallbackQueryHandler(join_roster, pattern='^join\.'))
    updater.dispatcher.add_handler(CallbackQueryHandler(add_to_roster, pattern='^addtoroster\.'))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    if IS_DEV:
        main()
    # routine(None, None)