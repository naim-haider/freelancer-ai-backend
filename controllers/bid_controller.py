from flask import jsonify, request, session
from models.bid_model import (
    create_bid,
    get_user_bids,
    get_all_bids,
    update_bid,
    delete_bid
)
from datetime import datetime

def add_bid():
    data = request.get_json()
    user_email = session.get("email")

    if not user_email:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    title = data.get("title")
    role = data.get("role")
    link = data.get("link")
    amount = data.get("amount")
    period = data.get("period")
    bid_text = data.get("bid_text")
    status = data.get("status", "stored")

    bid_id = create_bid(user_email, title, link, amount, period, bid_text, status)

    return jsonify({
        "success": True,
        "message": "Bid stored successfully in MongoDB",
        "bid_id": bid_id
    }), 201


def get_my_bids():
    user_email = session.get("email")
    if not user_email:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    bids = get_user_bids(user_email)
    for bid in bids:
        bid["_id"] = str(bid["_id"])
    return jsonify({"success": True, "bids": bids})


def get_all_user_bids():
    bids = get_all_bids()
    for bid in bids:
        bid["_id"] = str(bid["_id"])
    return jsonify({"success": True, "bids": bids})


def edit_bid(bid_id):
    data = request.get_json()
    updated_fields = {k: v for k, v in data.items() if k in ["title", "link", "amount", "period", "bid_text", "status"]}

    if not updated_fields:
        return jsonify({"success": False, "error": "No valid fields provided"}), 400

    updated = update_bid(bid_id, updated_fields)
    if not updated:
        return jsonify({"success": False, "error": "Bid not found or not updated"}), 404

    return jsonify({"success": True, "message": "Bid updated successfully"})


def remove_bid(bid_id):
    deleted = delete_bid(bid_id)
    if not deleted:
        return jsonify({"success": False, "error": "Bid not found"}), 404

    return jsonify({"success": True, "message": "Bid deleted successfully"})
