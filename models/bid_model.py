from pymongo import MongoClient
from datetime import datetime
import os

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "freelancer_bids")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
bids_collection = db["bids"]

def create_bid(user_email, title, link, amount, period, bid_text, status="stored"):
    bid_data = {
        "user_email": user_email,
        "title": title,
        "link": link,
        "amount": amount,
        "period": period,
        "bid_text": bid_text,
        "status": status,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    result = bids_collection.insert_one(bid_data)
    return str(result.inserted_id)

def get_user_bids(user_email):
    return list(bids_collection.find({"user_email": user_email}).sort("created_at", -1))

def get_all_bids():
    return list(bids_collection.find().sort("created_at", -1))

def update_bid(bid_id, updated_data):
    from bson import ObjectId
    updated_data["updated_at"] = datetime.utcnow()
    result = bids_collection.update_one({"_id": ObjectId(bid_id)}, {"$set": updated_data})
    return result.modified_count > 0

def delete_bid(bid_id):
    from bson import ObjectId
    result = bids_collection.delete_one({"_id": ObjectId(bid_id)})
    return result.deleted_count > 0
