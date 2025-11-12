from flask import Blueprint
from controllers.bid_controller import (
    add_bid,
    get_my_bids,
    get_all_user_bids,
    edit_bid,
    remove_bid
)

bid_bp = Blueprint("bids", __name__)

bid_bp.route("/api/bids", methods=["POST"])(add_bid)
bid_bp.route("/api/bids/mine", methods=["GET"])(get_my_bids)
bid_bp.route("/api/bids/all", methods=["GET"])(get_all_user_bids)
bid_bp.route("/api/bids/<bid_id>", methods=["PUT"])(edit_bid)
bid_bp.route("/api/bids/<bid_id>", methods=["DELETE"])(remove_bid)
