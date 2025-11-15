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

@app.route('/search', methods=['POST'])
# @login_required
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

@app.route('/search_with_id', methods=['POST'])
# @login_required
def search_with_id():
    import time
    data = request.get_json()
    start_id = data.get('start_id')
    
    if not start_id:
        return jsonify({"error": "Project ID is required"}), 400
    
    try:
        start_id = int(start_id)
    except ValueError:
        return jsonify({"error": "Invalid project ID"}), 400

    HEADERS = {
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Freelancer-OAuth-V1": PROD_TOKEN
    }

    projects = []
    project_ids_checked = []
    current_id = start_id
    max_attempts = 50  
    attempts = 0

    print(f"🔍 Starting project search from ID {start_id} ...")

    while len(projects) < 20 and attempts < max_attempts:
        project_id = current_id
        project_ids_checked.append(project_id)

        try:
            url = f"https://www.freelancer.com/api/projects/0.1/projects/{project_id}/?full_description=true"
            r = requests.get(url, headers=HEADERS, timeout=10)

            # --- Handle Rate Limiting ---
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 5))
                print(f"⚠️ Rate limit hit at project {project_id}. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue

            # --- Handle successful project fetch ---
            if r.status_code == 200:
                response_data = r.json()
                if response_data.get('status') == 'success':
                    project = response_data.get('result')
                    if project:
                        projects.append(project)
                        print(f"✅ Project {project_id} added ({len(projects)} found)")
            else:
                print(f"⏭️ Skipping project {project_id}, HTTP {r.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching project {project_id}: {e}")

        # Delay between requests to prevent API rate limit
        time.sleep(0.3)
        current_id += 1
        attempts += 1

    # --- No projects found case ---
    if not projects:
        return jsonify({
            "error": "No projects found in this ID range",
            "checked_ids": project_ids_checked
        }), 404

    # --- Collect all unique owner IDs ---
    owner_ids = list(set(p.get('owner_id') for p in projects if p.get('owner_id')))
    clients_data = {}

    # --- Fetch all client data in bulk ---
    if owner_ids:
        try:
            user_ids_param = '&'.join([f'users[]={uid}' for uid in owner_ids])
            users_url = f"https://www.freelancer.com/api/users/0.1/users/?{user_ids_param}&employer_reputation=true&jobs=true"
            
            users_response = requests.get(users_url, headers=HEADERS, timeout=15)

            if users_response.status_code == 429:
                retry_after = int(users_response.headers.get("Retry-After", 5))
                print(f"Rate limit hit while fetching users. Waiting {retry_after}s...")
                time.sleep(retry_after)
                users_response = requests.get(users_url, headers=HEADERS, timeout=15)

            users_response.raise_for_status()
            users_result = users_response.json()

            if users_result.get('status') == 'success':
                clients_data = users_result.get('result', {}).get('users', {})

        except requests.exceptions.RequestException as e:
            print(f"Warning: Could not fetch client data: {e}")

    # --- Format the data for frontend ---
    formatted_projects = []
    for project in projects:
        budget_info = project.get('budget', {}) or {}
        currency_info = project.get('currency', {}) or {}
        bid_stats = project.get('bid_stats', {}) or {}
        owner_id = project.get('owner_id')

        client_info = clients_data.get(str(owner_id), {}) if owner_id else {}
        employer_reputation = client_info.get('employer_reputation', {}) or {}
        entire_history = employer_reputation.get('entire_history', {}) or {}
        location = client_info.get('location', {}) or {}
        country_info = location.get('country', {}) or {}

        formatted_projects.append({
            'id': project.get('id'),
            'seo_url': project.get('seo_url'),
            'title': project.get('title', 'N/A'),
            'preview_description': (project.get('preview_description') or '').strip(),
            'description': (project.get('description') or '').strip(),
            'budget': {
                'minimum': budget_info.get('minimum', 0),
                'maximum': budget_info.get('maximum', 0)
            },
            'currency': {
                'code': currency_info.get('code', 'NA')
            },
            'bid_stats': {
                'bid_count': bid_stats.get('bid_count', 0),
                'bid_avg': round(float(bid_stats.get('bid_avg') or 0), 2)
            },
            'client': {
                'id': owner_id,
                'country': country_info.get('name', 'N/A'),
                'rating': {
                    'overall': entire_history.get('overall'),
                    'on_budget': entire_history.get('on_budget'),
                    'on_time': entire_history.get('on_time'),
                    'positive': entire_history.get('positive'),
                    'reviews': entire_history.get('reviews'),
                    'completion_rate': entire_history.get('completion_rate'),
                },
            }
        })

    print(f"Search complete: {len(formatted_projects)} valid projects found from ID {start_id} to {current_id - 1}")

    return jsonify({
        'projects': formatted_projects,
        'start_id': start_id,
        'end_id': current_id - 1,
        'total_found': len(formatted_projects),
        'checked_ids': project_ids_checked
    })


@app.route('/generate', methods=['POST'])
# @login_required
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
# @login_required
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
def place_bid():
    """
    Places a bid and stores it in MongoDB with user information from frontend.
    Expects user_id, user_email, and username in the request body.
    """
    data = request.get_json() or {}

    # Project details
    project_id = data.get('project_id')
    bid_text = data.get('bid')
    amount = float(data.get('amount', 50))
    period = int(data.get('period', 7))
    project_title = data.get('project_title') or "Untitled"
    project_url = data.get('project_url') or "#"

    # User details from frontend (from your Node.js auth)
    user_id = data.get('user_id')
    user_email = data.get('user_email')
    role = data.get('role')

    # Validation
    if not project_id or not bid_text:
        return jsonify({'error': 'Project ID and bid text required'}), 400
    
    if not user_id or not user_email:
        return jsonify({'error': 'User information required'}), 400

    # Duplicate Check - check if user already bid on this project
    existing_bid = bids_collection.find_one({
        "user_id": user_id,
        "link": project_url
    })
    
    if existing_bid:
        return jsonify({
            'success': False,
            'message': 'You have already bid on this project'
        }), 409

    # Try to get bidder ID from Freelancer API (optional)
    bidder_id = None
    try:
        url_self = "https://www.freelancer.com/api/users/0.1/self/"
        headers = {"Authorization": f"Bearer {PROD_TOKEN}"}
        response = requests.get(url_self, headers=headers, timeout=30)
        response.raise_for_status()
        bidder_id = response.json().get("result", {}).get("id")
    except Exception:
        bidder_id = None

    # Prepare bid payload for Freelancer API
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

    # Try to submit to Freelancer API
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

    # Store bid in MongoDB with user information
    bid_data = {
        "user_id": user_id,
        "user_email": user_email,
        "role": role,
        "username":  user_email.split('@')[0],
        "title": project_title,
        "link": project_url,
        "project_id": project_id,
        "amount": amount,
        "period": period,
        "bid_text": bid_text,
        "status": external_status,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = bids_collection.insert_one(bid_data)

    # Return response
    if external_status == "sent":
        return jsonify({
            "success": True,
            "message": "✅ Bid sent successfully!",
            "bid_id": str(result.inserted_id),
            "external": external_response
        }), 200
    elif external_status == "error":
        return jsonify({
            "success": True,
            "message": "⚠️ Bid stored locally (Freelancer API failed).",
            "bid_id": str(result.inserted_id),
            "external": external_response
        }), 202
    else:
        return jsonify({
            "success": True,
            "message": "✅ Bid saved locally (API not available).",
            "bid_id": str(result.inserted_id)
        }), 202
    

@app.route('/api/bids/tracker', methods=['GET'])
def get_bid_tracker():
    """
    Get bid tracker data. Expects user_id and role as query parameters.
    For admin: returns all users' bids grouped by user and date
    For user: returns only their bids grouped by date
    """
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    user_id = request.args.get('user_id')
    user_role = request.args.get('role', 'user')
    
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    
    # Date range for the selected month
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    
    if user_role in ['admin', 'super-admin']:
        # Get all bids for all users
        pipeline = [
            {
                '$match': {
                    'created_at': {
                        '$gte': start_date,
                        '$lt': end_date
                    }
                }
            },
            {
                '$group': {
                    '_id': {
                        'user_id': '$user_id',
                        'username': '$username',
                        'date': {
                            '$dateToString': {
                                'format': '%Y-%m-%d',
                                'date': '$created_at'
                            }
                        }
                    },
                    'bids': {
                        '$push': {
                            'id': {'$toString': '$_id'},
                            'title': '$title',
                            'link': '$link',
                            'amount': '$amount',
                            'period': '$period',
                            'bid_text': '$bid_text',
                            'status': '$status',
                            'created_at': '$created_at'
                        }
                    },
                    'total_count': {'$sum': 1},
                    'total_amount': {'$sum': '$amount'}
                }
            },
            {
                '$sort': {'_id.date': -1}
            }
        ]
        
        results = list(bids_collection.aggregate(pipeline))
        
        # Group by user
        users_data = {}
        for item in results:
            uid = item['_id']['user_id']
            uname = item['_id']['username']
            date = item['_id']['date']
            
            if uid not in users_data:
                users_data[uid] = {
                    'user_id': uid,
                    'username': uname,
                    'dates': {}
                }
            
            users_data[uid]['dates'][date] = {
                'date': date,
                'bids': item['bids'],
                'total_count': item['total_count'],
                'total_amount': item['total_amount']
            }
        
        return jsonify({
            'success': True,
            'year': year,
            'month': month,
            'is_admin': True,
            'users': list(users_data.values())
        })
    
    else:
        # Get only current user's bids
        pipeline = [
            {
                '$match': {
                    'user_id': user_id,
                    'created_at': {
                        '$gte': start_date,
                        '$lt': end_date
                    }
                }
            },
            {
                '$group': {
                    '_id': {
                        '$dateToString': {
                            'format': '%Y-%m-%d',
                            'date': '$created_at'
                        }
                    },
                    'bids': {
                        '$push': {
                            'id': {'$toString': '$_id'},
                            'title': '$title',
                            'link': '$link',
                            'amount': '$amount',
                            'period': '$period',
                            'bid_text': '$bid_text',
                            'status': '$status',
                            'created_at': '$created_at'
                        }
                    },
                    'total_count': {'$sum': 1},
                    'total_amount': {'$sum': '$amount'}
                }
            },
            {
                '$sort': {'_id': -1}
            }
        ]
        
        results = list(bids_collection.aggregate(pipeline))
        
        dates_data = {}
        for item in results:
            date = item['_id']
            dates_data[date] = {
                'date': date,
                'bids': item['bids'],
                'total_count': item['total_count'],
                'total_amount': item['total_amount']
            }
        
        return jsonify({
            'success': True,
            'year': year,
            'month': month,
            'is_admin': False,
            'dates': dates_data
        })


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
Write a compelling bid that MUST be under 1400 characters.

PROJECT CONTEXT:
Title: {title}
Description: {description}
{budget_text}

Write the bid in this EXACT format:

Hi there,

I understand you need [restate their main requirement in 3-4 sentences using details from description]. [Mention their key priority or concern].

Here's my approach:
* [Specific technical deliverable with methodology - 12-14 words]
* [User experience or interface feature - 10-12 words]
* [Additional value/feature - 10-12 words]
* [Documentation or support deliverable - 10-12 words]
* First working prototype delivered within [X] days
* All source code and documentation included

We specialize in [mention 2-3 technologies/skills directly relevant to this project]. I've built similar [project type] for clients in [relevant industries].

Recent work: https://www.mactix.com/projects
Logo, Graphics and Branding Work: https://www.mactix.com/freelancer

Quick questions:
1. [Practical clarification question about requirements - max 12 words]
2. [Question about preferences or technical details - max 12 words]

I can start immediately and have the first working version ready for your review within [timeframe]. Unlimited revisions until it meets your exact needs.

Let's discuss the details.

Best regards,
Team Mactix

CRITICAL CONSTRAINTS:
- TOTAL LENGTH: Maximum 1400 characters (count carefully!)
- Opening paragraph: 2-3 sentences, max 300 characters
- Approach bullets: 6 items, each 10-14 words maximum
- Expertise paragraph: 2 sentences, max 250 characters
- Portfolio: Keep exact format provided (2 lines)
- Questions: 2 questions, each max 12 words
- Closing: 3 sentences, max 150 characters

MANDATORY RULES:
1. Use asterisk (*) for bullet points, NOT (•)
2. NO markdown formatting (**, __, etc.)
3. NO emojis
4. Mention SPECIFIC technologies/tools from their description
5. Keep it concise - remove ALL unnecessary words
6. Use SHORT sentences (10-15 words each)
7. Only mention technologies relevant to THIS specific project
8. Questions must be practical and easy to answer
9. Timeline must be realistic: 24-48h simple, 3-7 days complex

CHARACTER SAVING TIPS:
- Use "I've" instead of "I have"
- Use "you need" instead of "you are looking for"
- Combine related ideas into single sentences
- Remove filler words: very, really, quite, just, actually
- Use commas instead of "and" where possible

EXAMPLE FORMAT (DO NOT COPY, just follow structure):
Hi there,

I understand you need a [specific solution]. [Their priority].

Here's my approach:
* [Technical approach - brief]
* [Feature/functionality - brief]
* [Added value - brief]
* [Support/docs - brief]
* First prototype within X days
* All files included

We specialize in [2-3 relevant skills]. I've built similar [type] for [industry] clients.

Recent work: https://www.mactix.com/projects
Logo, Graphics and Branding Work: https://www.mactix.com/freelancer

Quick questions:
1. [Short question]
2. [Short question]

I can start immediately and deliver within [time]. Unlimited revisions.

Let's discuss the details.

Best regards,
Team Mactix

Now write the bid. Count characters and ensure it's under 1400.
"""

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
