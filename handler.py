# import random
# import pymongo
# import requests
# import datetime
import os
import sys
import json

if "TELEGRAM_TOKEN" not in os.environ:
    arg_token = sys.argv[1]
    os.environ["TELEGRAM_TOKEN"] = arg_token # TELEGRAM_TOKEN
    print("TELEGRAM_TOKEN: " + os.environ["TELEGRAM_TOKEN"])

if "MONGODB_URI" not in os.environ:
    arg_uri = sys.argv[2]
    os.environ["MONGODB_URI"] = arg_uri # MONGODB_URI
    print('MONGODB_URI: ' + os.environ["MONGODB_URI"])

from telegram import (
    Update,
    # Bot,
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
    # ConversationHandler,
    Dispatcher,
    Filters,
    MessageHandler,
    Updater,
)

from commands import (
    start,
    show_duties,
    # create_duties,
    show_rosters,
    # next_duty,
    # mark_as_done,
    # remind,
    # get_chat_id,
    # reschedule,
    # add_to_waitlist,
    # create_roster,
    # join_roster_select,
    # join_roster,
    # add_to_new_roster,
    # add_to_roster,
    # mark_roster_as_done,
    # leave_roster_select,
    # leave_roster,
    # send_beta_v2,
    whitelist_user,
    check_whitelist,
    save_chat_group,
    # delete_roster_select,
    # delete_roster,
    cancel_callback,
)

from add_chore import (
    add_command,
    receive_roster_name,
    add_new_chore_callback,
    add_chore_day_callback,
    add_chore_single,
    add_chore_weekly,
    add_existing_chore_callback,
)

from done_chore import (
    done_command,
    mark_duty_as_done_callback,
)

from delete_chore import (
    delete_command,
    delete_duty_callback,
    delete_duty_single_callback,
    delete_duty_weekly_callback,
)

from edit_chore import (
    edit_command,
    edit_duty_callback,
    reschedule_duty_callback,
    reschedule_duty_date_callback,
    reschedule_duty_single_callback,
    reschedule_duty_weekly_callback,
)

from helpers import (
    configure_telegram,
)

from logger import logger

OK_RESPONSE = {
    'statusCode': 200,
    'headers': {'Content-Type': 'application/json'},
    'body': json.dumps('ok')
}
ERROR_RESPONSE = {
    'statusCode': 400,
    'body': json.dumps('Oops, something went wrong!')
}

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
    dispatcher.add_handler(CommandHandler("chores", check_whitelist(show_duties)))
    dispatcher.add_handler(CommandHandler("dutyroster", check_whitelist(show_rosters)))
    dispatcher.add_handler(CallbackQueryHandler(cancel_callback, pattern=r'^cancel$'))
    # dispatcher.add_handler(CommandHandler("addchore", check_whitelist(create_roster)))
    # dispatcher.add_handler(CommandHandler("done", check_whitelist(mark_as_done)))
    # dispatcher.add_handler(CommandHandler("join", check_whitelist(join_roster_select)))
    # dispatcher.add_handler(CommandHandler("leave", check_whitelist(leave_roster_select)))
    # dispatcher.add_handler(CommandHandler("deleteroster", check_whitelist(delete_roster_select)))
    # dispatcher.add_handler(CommandHandler("reschedule", check_whitelist(reschedule)))
    # dispatcher.add_handler(CommandHandler("editduty", check_whitelist(editduty)))
    # dispatcher.add_handler(CommandHandler("nextduty", check_whitelist(next_duty)))

    # Callback handlers
    # dispatcher.add_handler(CallbackQueryHandler(join_roster, pattern=r'^(joinnewroster|join)\.'))
    # dispatcher.add_handler(CallbackQueryHandler(add_to_new_roster, pattern=r'^addtonewroster\.'))
    # dispatcher.add_handler(CallbackQueryHandler(add_to_roster, pattern=r'^addtoroster\.'))
    # dispatcher.add_handler(CallbackQueryHandler(mark_roster_as_done, pattern=r'^rosterdone\.'))
    # dispatcher.add_handler(CallbackQueryHandler(leave_roster, pattern=r'^leave\.'))
    # dispatcher.add_handler(CallbackQueryHandler(delete_roster, pattern=r'^deleteroster\.'))

    # v3 add chore
    dispatcher.add_handler(CommandHandler("add", check_whitelist(add_command)))
    dispatcher.add_handler(MessageHandler(Filters.reply & ~Filters.command, check_whitelist(receive_roster_name)))
    dispatcher.add_handler(CallbackQueryHandler(add_new_chore_callback, pattern=r'^addnewchore$'))
    dispatcher.add_handler(CallbackQueryHandler(add_existing_chore_callback, pattern=r'^addexistingchore\.'))
    dispatcher.add_handler(CallbackQueryHandler(add_chore_day_callback, pattern=r'^addchoreday\.'))
    dispatcher.add_handler(CallbackQueryHandler(add_chore_single, pattern=r'^addchoresingle'))
    dispatcher.add_handler(CallbackQueryHandler(add_chore_weekly, pattern=r'^addchoreweekly'))

    # v3 done chore
    dispatcher.add_handler(CommandHandler("done", check_whitelist(done_command)))
    dispatcher.add_handler(CallbackQueryHandler(mark_duty_as_done_callback, pattern=r'^dutydone'))

    # v3 delete chore
    dispatcher.add_handler(CommandHandler("delete", check_whitelist(delete_command)))
    dispatcher.add_handler(CallbackQueryHandler(delete_duty_callback, pattern=r'^deleteduty\.'))
    dispatcher.add_handler(CallbackQueryHandler(delete_duty_single_callback, pattern=r'^deletedutysingle\.'))
    dispatcher.add_handler(CallbackQueryHandler(delete_duty_weekly_callback, pattern=r'^deletedutyweekly\.'))

    # v3 edit chore
    dispatcher.add_handler(CommandHandler("edit", check_whitelist(edit_command)))
    dispatcher.add_handler(CallbackQueryHandler(edit_duty_callback, pattern=r'^editduty\.'))
    dispatcher.add_handler(CallbackQueryHandler(reschedule_duty_callback, pattern=r'^rescheduleduty\.'))
    dispatcher.add_handler(CallbackQueryHandler(reschedule_duty_date_callback, pattern=r'^rescheduledutydate\.'))
    dispatcher.add_handler(CallbackQueryHandler(reschedule_duty_single_callback, pattern=r'^rescheduledutysingle\.'))
    dispatcher.add_handler(CallbackQueryHandler(reschedule_duty_weekly_callback, pattern=r'^rescheduledutyweekly\.'))

    # Beta message
    dispatcher.add_handler(CommandHandler("welcome", whitelist_user))
    # dispatcher.add_handler(MessageHandler(blacklisted_filter, send_beta_v2))
    dispatcher.add_handler(ChatMemberHandler(save_chat_group))

def main():
    TOKEN = os.environ["TELEGRAM_TOKEN"]

    updater = Updater(TOKEN)
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