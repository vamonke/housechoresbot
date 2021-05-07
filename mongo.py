import pymongo
import os

import logger

MONGODB_URI = 'mongodb+srv://vamonke:bDlccB4w6Ads4jmk@housechores.cerl9.mongodb.net/housechores?retryWrites=true&w=majority'
# MONGODB_URI = 'mongodb://localhost:27017/'
# MONGODB_URI = os.environ.get('MONGODB_URI')
# TEST_MONGODB_URI = 'mongodb://localhost:27017/'
# ENVIRONMENT = os.environ.get('ENVIRONMENT')

# MONGODB_URI = os.environ.get('MONGODB_URI') if ENVIRONMENT is 'prod' else TEST_MONGODB_URI

def setup_mongodb():
    """
    Setup mongodb client with mongodb uri.
    Returns a mongodb database instance.
    """

    if not MONGODB_URI:
        logger.error('The MONGODB_URI must be set')
        raise NotImplementedError

    mongo_client = pymongo.MongoClient(MONGODB_URI)
    database_name = "housechores"
    mongo_db = mongo_client[database_name]
    return mongo_db

mongo_db = setup_mongodb()

Chats = mongo_db['chats']
Schedules = mongo_db['schedules']
Rosters = mongo_db['rosters']
Duties = mongo_db['duties']
Users = mongo_db['users']
Waitlist = mongo_db['waitlist']