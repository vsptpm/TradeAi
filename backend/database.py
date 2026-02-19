from pymongo import MongoClient

from config import settings

client = MongoClient(settings.MONGODB_URI)
db = client["TradingAppDB"]

users_collection = db["users"]

# Ensure unique index on username
users_collection.create_index("username", unique=True)
