
import random
import requests
import os
import json
import datetime
from bson.objectid import ObjectId
from urllib.parse import urlencode

from telegram import User

from mongo import (
    # Chats,
    # Schedules,
    # Rosters,
    # Duties,
    Users
)

from logger import logger

user_properties = [
    'id',
    'first_name',
    'last_name',
    'username',
    'is_bot',
    'language_code',
]

def get_name_from_user_id(user_id):
    user_dict = Users.find_one({ 'id': user_id })
    if user_dict is None:
        return "❓"
    user = User(**user_dict)
    return user.mention_markdown_v2()

def get_user_dict_from_user(user):
    user_dict = { k: v for k, v in user.__dict__.items() if k in user_properties }
    return user_dict