import datetime
from telegram import (
    Update,
    # constants,
    ForceReply,
)
from telegram.ext import CallbackContext

from mongo import Feedback
from logger import logger
from add_chore import receive_roster_name
from helpers import alert_creator

HOUSE_CHORES_BOT_ID = 1783406286
DUTY_ROSTER_BOT_ID = 1798724954

def feedback_command(update: Update, context: CallbackContext):
    """
        /feedback: Ask user for feedback
    """
    if context.args:
        return receive_feedback(update, context)

    message = fr"💬 Have a suggestion or found a bug\? Let me know by replying to this message\."

    logger.info('Reply message:\n' + message)
    update.message.reply_markdown_v2(
        text=message,
        quote=False,
        reply_markup=ForceReply(selective=True),
    )

def receive_feedback(update: Update, context: CallbackContext):
    """
        /feedback -> (text)
        Save feedback and inform author
    """
    user = update.effective_user
    user_text = user.mention_markdown_v2()
    user_id = user.id

    chat_id = update.message.chat.id

    feedback_text = update.message.text
    if context.args:
        feedback_text = " ".join(context.args)

    Feedback.insert_one({
        'chat_id': chat_id,
        'user_id': user_id,
        'text': feedback_text,
        'createdAt': datetime.datetime.now(),
    })

    message = fr"📮 Feedback received\, {user_text}\. Thanks for helping to improve me\!"

    update.message.reply_markdown_v2(
        text=message,
        quote=False,
    )

    creator_message = fr"📮 Feedback received from {user_text}:" + "\n" + feedback_text
    alert_creator(creator_message)

def reply_message_handler(update: Update, context: CallbackContext):
    """Check reply message and call respective callback functions"""
    
    # Verify if message is reply to bot create_roster message

    # Check sender of create_roster message
    message = update.effective_message
    reply_to_message = message.reply_to_message
    user_to_reply_id = reply_to_message.from_user.id
    if user_to_reply_id not in [HOUSE_CHORES_BOT_ID, DUTY_ROSTER_BOT_ID]:
        return
    
    message_to_reply = reply_to_message.text

    # Check content of create_roster message
    roster_name_substring = 'what\'s the name of the chore?'
    if roster_name_substring in message_to_reply:
        return receive_roster_name(update, context)

    # Check content of feedback message
    feedback_substring = 'Have a suggestion or found a bug? Let me know by replying to this message.'
    message_to_reply = reply_to_message.text
    if feedback_substring in message_to_reply:
        return receive_feedback(update, context)