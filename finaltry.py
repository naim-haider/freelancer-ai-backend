from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
import requests
import sys
import json
import webbrowser
import threading
from functools import wraps
from datetime import datetime, timedelta, date
import os
from flask_cors import CORS
from dotenv import load_dotenv
import jwt
import time
from requests.exceptions import RequestException, HTTPError
from routes.bid_routes import bid_bp
from models.bid_model import create_bid, get_user_bids
from bson import ObjectId
from pymongo import MongoClient

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["freelancer_bids"]
bids_collection = db["bids"]

app.register_blueprint(bid_bp)

# Allow CORS for all routes and methods
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

app.secret_key = os.getenv('SECRET_KEY', 'default_secret')

# --- CONFIGURATION ---
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
PROD_TOKEN = os.getenv('PROD_TOKEN')

# Directory to store bids
BIDS_ROOT = os.path.join(os.path.dirname(__file__), "bids")


# ----------------- Utilities for bid storage (file-based) -----------------
# def ensure_dir(path):
#     if not os.path.exists(path):
#         os.makedirs(path, exist_ok=True)


# def month_folder_for(dt: date):
#     return os.path.join(BIDS_ROOT, f"{dt.year}-{dt.month:02d}")


# def user_file_for(dt: date, username: str):
#     folder = month_folder_for(dt)
#     ensure_dir(folder)
#     return os.path.join(folder, f"{username}.json")


# def load_user_bids_file(path):
#     if os.path.exists(path):
#         try:
#             with open(path, "r", encoding="utf-8") as fh:
#                 return json.load(fh)
#         except Exception:
#             # if corrupt, return empty
#             return {}
#     return {}


# def save_user_bids_file(path, data):
#     with open(path, "w", encoding="utf-8") as fh:
#         json.dump(data, fh, indent=2, ensure_ascii=False)


# def cleanup_old_data(keep_days=31):
#     """Remove bid files that are older than keep_days based on folder name YYYY-MM."""
#     cutoff_date = datetime.utcnow().date() - timedelta(days=keep_days)
#     if not os.path.exists(BIDS_ROOT):
#         return
#     for name in os.listdir(BIDS_ROOT):
#         folder_path = os.path.join(BIDS_ROOT, name)
#         if not os.path.isdir(folder_path):
#             continue
#         # folder name expected 'YYYY-MM'
#         try:
#             y, m = name.split("-")
#             folder_date = date(int(y), int(m), 1)
#         except Exception:
#             # unexpected folder name - skip
#             continue
#         if folder_date < date(cutoff_date.year, cutoff_date.month, 1):
#             try:
#                 for f in os.listdir(folder_path):
#                     try:
#                         os.remove(os.path.join(folder_path, f))
#                     except Exception:
#                         pass
#                 try:
#                     os.rmdir(folder_path)
#                 except Exception:
#                     pass
#             except Exception:
#                 pass


# def store_bid_local(username: str, title: str, link: str, amount: float, period: int, bid_text: str, status: str = "stored"):
#     """
#     Store a bid for username under today's date.
#     Data layout per user-file:
#     {
#       "YYYY-MM-DD": [
#          { "time": "HH:MM:SS", "title": "...", "link": "...", "amount": 50, "period": 7, "bid": "...", "status": "stored" }
#       ],
#       ...
#     }
#     """
#     cleanup_old_data(keep_days=31)

#     today = datetime.utcnow().date()
#     user_file = user_file_for(today, username)
#     data = load_user_bids_file(user_file)

#     day_key = today.isoformat()
#     entry = {
#         "time": datetime.utcnow().strftime("%H:%M:%S"),
#         "title": title,
#         "link": link,
#         "amount": amount,
#         "period": period,
#         "bid": bid_text,
#         "status": status
#     }
#     if day_key not in data:
#         data[day_key] = []
#     data[day_key].append(entry)

#     save_user_bids_file(user_file, data)
#     return True


# def gather_user_bids_for_month(username: str, year_month: str = None):
#     """
#     Return data for a given user for the month 'YYYY-MM' (defaults to current month).
#     """
#     if year_month is None:
#         now = datetime.utcnow()
#         year_month = f"{now.year}-{now.month:02d}"

#     folder = os.path.join(BIDS_ROOT, year_month)
#     if not os.path.exists(folder):
#         return {}

#     user_file = os.path.join(folder, f"{username}.json")
#     return load_user_bids_file(user_file)


# def gather_all_users_bids_for_month(year_month: str = None):
#     """
#     Return a dict of {username: user_data} for every user file in the given month folder.
#     """
#     if year_month is None:
#         now = datetime.utcnow()
#         year_month = f"{now.year}-{now.month:02d}"
#     folder = os.path.join(BIDS_ROOT, year_month)
#     if not os.path.exists(folder):
#         return {}
#     result = {}
#     for fname in os.listdir(folder):
#         if not fname.endswith(".json"):
#             continue
#         username = fname[:-5]
#         path = os.path.join(folder, fname)
#         result[username] = load_user_bids_file(path)
#     return result


# def user_has_bid_on_link(username: str, link: str) -> bool:
#     """
#     Scan all month folders under BIDS_ROOT for a user file and check if any entry has the same link.
#     This uses exact string match. If you want normalized comparison, add normalization here.
#     """
#     if not os.path.exists(BIDS_ROOT):
#         return False
#     for month_folder in os.listdir(BIDS_ROOT):
#         folder_path = os.path.join(BIDS_ROOT, month_folder)
#         if not os.path.isdir(folder_path):
#             continue
#         user_file = os.path.join(folder_path, f"{username}.json")
#         if not os.path.exists(user_file):
#             continue
#         data = load_user_bids_file(user_file)
#         for day, entries in data.items():
#             for e in entries:
#                 if e.get("link") == link:
#                     return True
#     return False


# ----------------- End bid storage utilities -----------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = session.get('token')
        if not token:
            return jsonify({'error': 'Unauthorized, please log in.'}), 401

        try:
            # Verify JWT using the Node backend's secret (or its public key if provided)
            secret_key = os.getenv('JWT_SECRET')
            decoded = jwt.decode(token, secret_key, algorithms=["HS256"])
            session['email'] = decoded.get('email') or decoded.get('email')
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Session expired, please log in again.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token.'}), 401

        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['POST'])
def login():
    """Authenticate user via Node backend and store JWT in session."""
    data = request.get_json()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not email or not password:
        return jsonify({'success': False, 'error': 'email and password required'}), 400

    node_api_url = os.getenv('NODE_API_URL')
    if not node_api_url:
        return jsonify({'success': False, 'error': 'Backend URL not configured'}), 500

    try:
        print(f"🔹 Sending login to NodeJS backend: {node_api_url}")
        response = requests.post(node_api_url, json={'email': email, 'password': password}, timeout=15)

        if response.status_code == 429:
            return jsonify({'success': False, 'error': 'Too many requests — please wait a minute and try again.'}), 429

        response.raise_for_status()
        result = response.json()

        token = result.get('token')
        user = result.get('user')

        if not token:
            return jsonify({'success': False, 'error': 'Token not provided by Node backend'}), 401

        session['logged_in'] = True
        session['email'] = email
        session['token'] = token

        return jsonify({'success': True, 'token': token, 'user': user})

    except HTTPError as e:
        return jsonify({'success': False, 'error': f"HTTP error: {e}"}), 500
    except RequestException as e:
        return jsonify({'success': False, 'error': f"Connection error: {e}"}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': f"Unexpected error: {e}"}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    return jsonify({"message": "Flask backend running!", "user": session.get('username')})



@app.route('/search', methods=['POST'])
@login_required
def search_projects():
    data = request.get_json()
    query = data.get('query', "").strip() if data else ""
    minp = data.get('minPrice')
    maxp = data.get('maxPrice')
    project_types = data.get('project_type')

    limit = 10

    url = (
        "https://www.freelancer.com/api/projects/0.1/projects/active/"
        f"?compact=&limit={limit}&full_description=true&project_types%5B%5D={project_types}"
        f"&max_avg_price={maxp}%3D&min_avg_price={minp}&query={query}"
    )

    HEADERS = {
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Freelancer-OAuth-V1": PROD_TOKEN
    }

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()

        if data.get('status') != 'success':
            return jsonify({"error": data.get('message', "Unknown API error")}), 500

        all_projects = data.get("result", {}).get("projects", [])
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error fetching projects: {e}"}), 500

    # Collect all unique owner IDs
    owner_ids = list(set(project.get('owner_id') for project in all_projects if project.get('owner_id')))

    # Fetch all client information in bulk
    clients_data = {}

    if owner_ids:
        try:
            # Fetch users in bulk with employer reputation
            user_ids_param = '&'.join([f'users[]={uid}' for uid in owner_ids])
            users_url = f"https://www.freelancer.com/api/users/0.1/users/?{user_ids_param}&employer_reputation=true&jobs=true"

            users_response = requests.get(users_url, headers=HEADERS, timeout=15)
            users_response.raise_for_status()
            users_result = users_response.json()

            if users_result.get('status') == 'success':
                users = users_result.get('result', {}).get('users', {})
                clients_data = users
        except requests.exceptions.RequestException as e:
            print(f"Warning: Could not fetch client data: {e}")

    projects = []

    for project in all_projects:
        budget_info = project.get('budget', {})
        currency_info = project.get('currency', {})

        bid_stats = project.get('bid_stats', {})
        bid_count = bid_stats.get('bid_count', 0)
        bid_avg = bid_stats.get('bid_avg', 0)

        owner_id = project.get('owner_id')

        # Get client information
        client_info = clients_data.get(str(owner_id), {}) if owner_id else {}

        # Extract employer reputation data
        employer_reputation = client_info.get('employer_reputation', {})
        entire_history = employer_reputation.get('entire_history', {})

        # Get category ratings
        category_ratings = entire_history.get('category_ratings', {})

        client_data = {
            'id': owner_id,
            'username': client_info.get('username', 'N/A'),
            'display_name': client_info.get('display_name', 'N/A'),
            'public_name': client_info.get('public_name'),
            'country': client_info.get('location', {}).get('country', {}).get('name', 'N/A'),
            'country_code': client_info.get('location', {}).get('country', {}).get('code'),
            'city': client_info.get('location', {}).get('city'),
            'registration_date': client_info.get('registration_date'),
            'profile_url': f"https://www.freelancer.com/u/{client_info.get('username', '')}" if client_info.get('username') else None,
            'avatar': client_info.get('avatar_large_cdn') or client_info.get('avatar_large') or client_info.get('avatar_cdn'),
            'company': client_info.get('company'),
            'role': client_info.get('role'),
            'chosen_role': client_info.get('chosen_role'),
            'rating': {
                'overall': entire_history.get('overall'),
                'on_budget': entire_history.get('on_budget'),
                'on_time': entire_history.get('on_time'),
                'positive': entire_history.get('positive'),
                'all': entire_history.get('all'),
                'reviews': entire_history.get('reviews'),
                'complete': entire_history.get('complete'),
                'incomplete': entire_history.get('incomplete'),
                'completion_rate': entire_history.get('completion_rate'),
                'rehire_rate': entire_history.get('rehire_rate'),
                'category_ratings': {
                    'clarity_spec': category_ratings.get('clarity_spec'),
                    'communication': category_ratings.get('communication'),
                    'payment_prom': category_ratings.get('payment_prom'),
                    'professionalism': category_ratings.get('professionalism'),
                    'work_for_again': category_ratings.get('work_for_again')
                }
            },
            'payment_verified': client_info.get('status', {}).get('payment_verified'),
            'email_verified': client_info.get('status', {}).get('email_verified'),
            'deposit_made': client_info.get('status', {}).get('deposit_made'),
            'identity_verified': client_info.get('status', {}).get('identity_verified'),
            'phone_verified': client_info.get('status', {}).get('phone_verified'),
            'limited_account': client_info.get('limited_account'),
            'membership_package': client_info.get('membership_package'),
        }

        projects.append({
            'id': project.get('id'),
            'seo_url': project.get('seo_url'),
            'title': project.get('title', 'N/A'),
            'preview_description': project.get('preview_description', '').strip(),
            'description': project.get('description', '').strip(),
            'budget': {
                'minimum': budget_info.get('minimum', 0),
                'maximum': budget_info.get('maximum', 0)
            },
            'currency': {
                'code': currency_info.get('code', 'NA')
            },
            'bid_stats': {
                'bid_count': bid_count,
                'bid_avg': round(bid_avg, 2)
            },
            'country': {
                'country': currency_info.get('country', 'NA')
            },
            'bidperiod': project.get('bidperiod', None),
            'client': client_data
        })

    return jsonify(projects)


@app.route('/generate', methods=['POST'])
@login_required
def generate_bid_route():
    """Generate a custom bid in your required structure."""
    data = request.get_json()
    project = data.get('project', {})
    user_details = data.get('userDetails', {})

    if not GEMINI_API_KEY:
        return jsonify({'error': 'Gemini API key is not configured.'}), 500

    prompt = create_personalized_prompt(project, user_details)

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        result = response.json()

        if 'candidates' in result and result['candidates'][0]['content']['parts'][0]['text']:
            bid_text = result['candidates'][0]['content']['parts'][0]['text']
            return jsonify({'bid': bid_text})
        else:
            return jsonify({'error': "AI returned no content."}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'AI service error: {e}'}), 500


@app.route('/generate_graphics', methods=['POST'])
@login_required
def generate_graphics_bid():
    """Generate a static graphics bid with project details."""
    data = request.get_json()
    project = data.get('project', {})
    user_details = data.get('userDetails', {}) 

    title = project.get('title', 'your project')

    graphics_bid = f"""Hello,
We will create Classic Logo for {title}, and I am excited to say that we can do this project with perfection.
 
We have talented graphic design team to design exclusive premium logos and all printing materials. We can create an awesome logo for your business.
 
Please message me to discuss this.
 
Check our work : https://www.freelancer.com/u/snehbharat
 
Here's what I offer:
• With in 24 hrs We will send you 6 logo option from 6 different designer to choose from.
• All artwork will be custom and NO USE of CLIPART
• Unlimited revisions (don't hesitate to request as many as you need)
• All the source files will be provided. (Ai-PSD-PDF-EPS-JPEG-PNG)
• High-resolution quality 100% Satisfaction Guaranteed. you will own the full copyright of the final design.
 
Revisions:
A good number of revisions based on your feedback to ensure the design aligns with your expectations.
 
We look forward to collaborating with you on this project. Please feel free to reach out for any clarifications or to set up a discovery call.
Warm regards,
Team Mactix"""

    return jsonify({'bid': graphics_bid})


@app.route('/place_bid', methods=['POST'])
@login_required
def place_bid():
    """
    Places a bid via Freelancer API (if possible)
    and always stores locally with duplicate prevention.
    """
    data = request.get_json() or {}

    project_id = data.get('project_id')
    bid_text = data.get('bid')
    amount = float(data.get('amount', 50))
    period = int(data.get('period', 7))
    project_title = data.get('project_title') or data.get('title') or "Untitled"
    project_url = data.get('project_url') or data.get('link') or "#"

    username = session.get('username')

    # --- Validation ---
    if not project_id or not bid_text:
        return jsonify({'error': 'Project ID and bid text required'}), 400

    # --- Duplicate Check ---
    if bids_collection.find_one({"user_email": username, "link": project_url}):
        return jsonify({
            'success': False,
            'message': 'Already bid'
        }), 409

    # --- Try to get bidder ID (Freelancer self) ---
    bidder_id = None
    try:
        url_self = "https://www.freelancer.com/api/users/0.1/self/"
        headers = {"Authorization": f"Bearer {PROD_TOKEN}"}
        response = requests.get(url_self, headers=headers, timeout=30)
        response.raise_for_status()
        bidder_id = response.json().get("result", {}).get("id")
    except Exception:
        bidder_id = None  # Not fatal — we'll still store locally

    # --- Prepare external bid payload ---
    bid_payload = {
        "project_id": project_id,
        "bidder_id": bidder_id,
        "amount": amount,
        "period": period,
        "milestone_percentage": 100,
        "description": bid_text
    }

    headers_post = {
        "Authorization": f"Bearer {PROD_TOKEN}",
        "Content-Type": "application/json"
    }

    external_status = "not_sent"
    external_response = None

    # --- Attempt external submission ---
    try:
        r = requests.post(
            "https://www.freelancer.com/api/projects/0.1/bids/",
            headers=headers_post,
            json=bid_payload,
            timeout=30
        )
        external_response = r.json()
        if r.status_code < 400:
            external_status = "sent"
        else:
            external_status = "error"
    except requests.exceptions.RequestException:
        external_status = "error"

# --- Store bid in MongoDB ---
    create_bid(
        user_email=username,
        title=project_title,
        link=project_url,
        amount=amount,
        period=period,
        bid_text=bid_text,
        status=external_status
    )

    # --- Build response for frontend ---
    if external_status == "sent":
        return jsonify({
            "success": True,
            "message": "✅ Bid sent successfully!",
            "external": external_response
        }), 200

    elif external_status == "error":
        return jsonify({
            "success": True,
            "message": "⚠️ Bid stored locally (Freelancer API failed).",
            "external": external_response
        }), 202

    else:
        return jsonify({
            "success": True,
            "message": "✅ Bid saved locally (API not available)."
        }), 202
# -------------------- Bid Insight routes --------------------

# @app.route('/bid_insight')
# @login_required
# def bid_insight_page():
#     username = session.get('username')
#     is_admin = username == 'admin'
#     return jsonify({"message": "Bid insight page (handled by React)", "user": username, "admin": is_admin})



# @app.route('/api/bid_insight', methods=['GET'])
# @login_required
# def api_bid_insight():
#     """
#     Returns JSON structure with bids for the current month.
#     If admin, returns all users.
#     Accepts optional query param month=YYYY-MM to fetch another month (if available).
#     """
#     username = session.get('username')
#     is_admin = (username == 'admin')

#     month = request.args.get('month')
#     if not month:
#         now = datetime.utcnow()
#         month = f"{now.year}-{now.month:02d}"

#     if is_admin:
#         all_data = gather_all_users_bids_for_month(month)
#         return jsonify({"month": month, "data": all_data})
#     else:
#         user_data = gather_user_bids_for_month(username, month)
#         return jsonify({"month": month, "data": {username: user_data}})

# -------------------- CUSTOM PROMPT BUILDER --------------------
def create_personalized_prompt(project, user_details):
    """Builds AI prompt for a structured Mactix-style bid."""
    title = project.get('title', '')
    description = project.get('description', '')
    budget = project.get('budget', {})
    currency = project.get('currency', {}).get('code', 'USD')

    min_b = budget.get('minimum', 0)
    max_b = budget.get('maximum', 0)
    budget_text = f"Budget: {min_b}-{max_b} {currency}" if min_b and max_b else ""

    return f"""
You are a professional bid writer at Mactix Global Solutions. 
Your job is to create a highly persuasive bid under 1500 characters 
based on the project details below.

Project Title: {title}
Description: {description}
{budget_text}

Write the bid in this exact structure (strictly maintain formatting):

Dear Hiring Manager, 
Greetings from Mactix Global Solutions!

Project Scope:
Summarize in 2-3 lines what this project is about and what client needs.

Our Approach:
Describe in 3-4 lines how we'll deliver it successfully — clear, confident, human tone.

We specialize in:
- Web & Mobile App Development
- UI/UX Design
- Frontend (React.js, Next.js) Backend (Node.js, JAVA)
- Python, AI/ML
- DevOps, AWS, GCP, Azure
- SEO & Digital Marketing

live work:
https://imecommunity.com
https://mentaljoga.com.pl
https://fortanden.dk
https://lostontheroute.com
https://www.healthyadhd.com
https://www.virayo.com
https://bmostadium.com
https://becurioustravel.com
https://bcbagelshop.com
https://www.delightoffice.hr 

Websites Work:
https://www.mactix.com/projects

Logo and Graphics Work:
https://www.mactix.com/freelancer

Questions for you:
1. [First simple question based on the project]
2. [Second simple question based on the project]

We look forward to collaborating with you. Please feel free to reach out for any clarifications.
Warm regards,
Team Mactix

Rules:
- Keep total bid under 1500 characters.
- Do NOT use markdown symbols (** or _).
- Use natural, human-friendly tone.
- Avoid emojis, hashtags, or robotic language.
- Ensure the result looks like it was typed by a professional business development manager.
- Keep Project Scope concise (2-3 lines).
- Keep Our Approach focused (3-4 lines).
- Ask TWO simple, easy-to-answer questions that are directly relevant to the project description.
- Each question must be on a SEPARATE LINE numbered as 1. and 2.
- Questions should demonstrate you understand the requirements and want basic clarifications.
- Keep questions straightforward - avoid complex or technical questions.
"""


def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
