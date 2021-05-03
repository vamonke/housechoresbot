import random
import pymongo
import logging
import requests
import os
import json
import datetime
import pprint
from urllib.parse import urlencode

from telegram import Update, ForceReply, Bot, User, InlineKeyboardMarkup, InlineKeyboardButton, constants
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CommandHandler, CallbackQueryHandler, CallbackContext, Filters, ConversationHandler

from commands import start, join, leave, show_duties, create_duties, create_schedule, show_schedule, next_duty, mark_as_done, callback_handler, remind, get_chat_id, reschedule, add_to_waitlist

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
is_dev = False

user_properties = [
    'id',
    'first_name',
    'last_name',
    'username',
    'is_bot',
    'language_code',
]

LIM_FAMILY_USER_IDS = [
    265435469, # VAMONKE
    808439673,
    278239097,
    59546722,
]

VAMONKE_ID = 265435469

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
    if message is not None:
        update.message.reply_markdown_v2(message, quote=False)
        logger.info(message)

    message = fr"Someone spoke to HouseChoresBot\! ❓"
    if update.effective_user is not None:
        user_text = update.effective_user.mention_markdown_v2()
        message = fr"{user_text} spoke to HouseChoresBot\! 😀"

    alert_creator(message)

def alert_creator(message):
    bot = configure_telegram()
    bot.send_message(
        chat_id=VAMONKE_ID,
        text=message,
        parse_mode=constants.PARSEMODE_MARKDOWN_V2,
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

        reply_markup = None
        message = None

        if update.effective_user is None or update.effective_user.id not in LIM_FAMILY_USER_IDS:
            send_beta(update)
            return OK_RESPONSE

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
            elif text == '/leave':
                message = leave(update)
            elif text == '/duties':
                message = show_duties(update)
            elif text == '/createduties':
                message = create_duties()
            elif text == '/createschedule':
                message = create_schedule(update)
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

def function_wrapper(fn, update):
    print('Running', fn.__name__)
    if update.effective_user is None or update.effective_user.id not in LIM_FAMILY_USER_IDS:
        send_beta(update)
    else:
        message = fn(update)
        reply_markup = None

        if type(message) is tuple:
            message, reply_markup = message

        if message is not None:
            update.message.reply_markdown_v2(
                text=message,
                reply_markup=reply_markup
            )

def dev():
    TEST_TELEGRAM_TOKEN = '1798724954:AAGuKOTuVWX8qfuRLUx1EU82Di9czAR6kFs'
    updater = Updater(TEST_TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher

    # dispatcher.add_handler(CommandHandler("join", lambda update, _ : function_wrapper(join, update)))
    # dispatcher.add_handler(CommandHandler("leave", lambda update, _ : function_wrapper(leave, update)))
    # dispatcher.add_handler(CommandHandler("duties", lambda update, _ : function_wrapper(show_duties, update)))
    # dispatcher.add_handler(CommandHandler("createduties", lambda update, _ : function_wrapper(create_duties, update)))
    # dispatcher.add_handler(CommandHandler("createschedule", lambda update, _ : function_wrapper(create_schedule, update)))
    # dispatcher.add_handler(CommandHandler("schedule", lambda update, _ : function_wrapper(show_schedule, update)))
    dispatcher.add_handler(CommandHandler("start", lambda update, _ : function_wrapper(start, update)))
    # dispatcher.add_handler(CommandHandler("nextduty", lambda update, _ : function_wrapper(next_duty, update)))
    # dispatcher.add_handler(CommandHandler("done", lambda update, _ : function_wrapper(mark_as_done, update)))
    # dispatcher.add_handler(CommandHandler("reschedule", lambda update, _ : function_wrapper(reschedule, update)))

    updater.dispatcher.add_handler(CallbackQueryHandler(lambda update, _ : function_wrapper(callback_handler, update)))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    is_dev = True
    dev()
    # routine(None, None)