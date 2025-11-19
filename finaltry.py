from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
import requests
import sys
import json
import webbrowser
import threading
from functools import wraps
from datetime import datetime, timedelta, timezone
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
import pytz

ist = pytz.timezone("Asia/Kolkata")

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
def search_with_id():
    import time
    data = request.get_json()
    start_id = data.get('start_id')
    direction = data.get('direction', 'forward')  # Get search direction
    
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
    
    # Determine direction increment
    id_increment = 1 if direction == 'forward' else -1

    print(f"🔍 Starting project search from ID {start_id} ({direction})...")

    while len(projects) < 20 and attempts < max_attempts:
        project_id = current_id
        
        # Stop if we go below ID 1 when going backward
        if project_id < 1:
            break
            
        project_ids_checked.append(project_id)

        try:
            url = f"https://www.freelancer.com/api/projects/0.1/projects/{project_id}/?full_description=true"
            r = requests.get(url, headers=HEADERS, timeout=10)

            # Handle Rate Limiting
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 5))
                print(f"⚠️ Rate limit hit at project {project_id}. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue

            # Handle successful project fetch
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
        current_id += id_increment
        attempts += 1

    # Calculate last checked ID (the last one we actually checked)
    last_checked_id = current_id - id_increment

    # No projects found case
    if not projects:
        return jsonify({
            "error": "No projects found in this ID range",
            "checked_ids": project_ids_checked,
            "last_checked_id": last_checked_id,  # Include even on error
            "direction": direction
        }), 404

    # Collect all unique owner IDs
    owner_ids = list(set(p.get('owner_id') for p in projects if p.get('owner_id')))
    clients_data = {}

    # Fetch all client data in bulk
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

    # Format the data for frontend
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

    # Calculate proper start/end IDs based on direction
    if direction == 'forward':
        actual_start_id = start_id
        actual_end_id = last_checked_id
    else:  # backward
        actual_start_id = last_checked_id
        actual_end_id = start_id

    print(f"✅ Search complete: {len(formatted_projects)} projects found")
    print(f"📊 ID range: {actual_start_id} to {actual_end_id}")
    print(f"🎯 Last checked ID: {last_checked_id}")

    return jsonify({
        'projects': formatted_projects,
        'start_id': actual_start_id,
        'end_id': actual_end_id,
        'last_checked_id': last_checked_id,  # IMPORTANT: Return this!
        'total_found': len(formatted_projects),
        'checked_ids': project_ids_checked,
        'direction': direction
    })

@app.route('/search_single_project', methods=['POST'])
def search_single_project():
    data = request.get_json()
    project_id = data.get('project_id')
    
    if not project_id:
        return jsonify({"error": "Project ID is required"}), 400
    
    try:
        project_id = int(project_id)
    except ValueError:
        return jsonify({"error": "Invalid project ID"}), 400

    HEADERS = {
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Freelancer-OAuth-V1": PROD_TOKEN
    }

    try:
        url = f"https://www.freelancer.com/api/projects/0.1/projects/{project_id}/?full_description=true"
        r = requests.get(url, headers=HEADERS, timeout=10)

        # Handle Rate Limiting
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 5))
            return jsonify({
                "error": f"Rate limit hit. Please wait {retry_after} seconds."
            }), 429

        # Handle successful project fetch
        if r.status_code == 200:
            response_data = r.json()
            if response_data.get('status') == 'success':
                project = response_data.get('result')
                if not project:
                    return jsonify({"error": f"Project {project_id} not found"}), 404
            else:
                return jsonify({"error": "Project not found or not accessible"}), 404
        else:
            return jsonify({"error": f"Project {project_id} not found (HTTP {r.status_code})"}), 404

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error fetching project: {str(e)}"}), 500

    # Get owner ID
    owner_id = project.get('owner_id')
    client_info = {}

    # Fetch client data if owner exists
    if owner_id:
        try:
            users_url = f"https://www.freelancer.com/api/users/0.1/users/?users[]={owner_id}&employer_reputation=true&jobs=true"
            users_response = requests.get(users_url, headers=HEADERS, timeout=15)

            if users_response.status_code == 429:
                retry_after = int(users_response.headers.get("Retry-After", 5))
                time.sleep(retry_after)
                users_response = requests.get(users_url, headers=HEADERS, timeout=15)

            if users_response.status_code == 200:
                users_result = users_response.json()
                if users_result.get('status') == 'success':
                    users_data = users_result.get('result', {}).get('users', {})
                    client_info = users_data.get(str(owner_id), {})

        except requests.exceptions.RequestException as e:
            print(f"Warning: Could not fetch client data: {e}")

    # Format the project data
    budget_info = project.get('budget', {}) or {}
    currency_info = project.get('currency', {}) or {}
    bid_stats = project.get('bid_stats', {}) or {}
    
    employer_reputation = client_info.get('employer_reputation', {}) or {}
    entire_history = employer_reputation.get('entire_history', {}) or {}
    location = client_info.get('location', {}) or {}
    country_info = location.get('country', {}) or {}

    formatted_project = {
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
        'bidperiod': project.get('bidperiod', None),
        'client': {
            'id': owner_id,
            'username': client_info.get('username', 'N/A'),
            'display_name': client_info.get('display_name', 'N/A'),
            'country': country_info.get('name', 'N/A'),
            'country_code': country_info.get('code'),
            'city': location.get('city'),
            'profile_url': f"https://www.freelancer.com/u/{client_info.get('username', '')}" if client_info.get('username') else None,
            'rating': {
                'overall': entire_history.get('overall'),
                'on_budget': entire_history.get('on_budget'),
                'on_time': entire_history.get('on_time'),
                'positive': entire_history.get('positive'),
                'reviews': entire_history.get('reviews'),
                'completion_rate': entire_history.get('completion_rate'),
            },
            'payment_verified': client_info.get('status', {}).get('payment_verified'),
            'email_verified': client_info.get('status', {}).get('email_verified'),
        }
    }

    return jsonify({
        'project': formatted_project,
        'project_id': project_id
    })

@app.route('/generate', methods=['POST'])
def generate_bid_route():
    """Generate a custom bid with robust error handling and retries."""
    data = request.get_json()
    project = data.get('project', {})
    user_details = data.get('userDetails', {})

    if not GEMINI_API_KEY:
        return jsonify({'error': 'Gemini API key is not configured.'}), 500

    # Create the prompt
    prompt = create_personalized_prompt(project, user_details)
    
    # Log prompt length for debugging
    print(f"📝 Prompt length: {len(prompt)} characters")

    # Try with Gemini 2.5 Flash first (faster, cheaper)
    models = [
        "gemini-2.5-flash-preview-05-20",
        "gemini-1.5-flash",  # Fallback 1
        "gemini-1.5-pro"     # Fallback 2 (more reliable)
    ]
    
    headers = {'Content-Type': 'application/json'}
    
    for i, model in enumerate(models):
        try:
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 2048,
                },
                "safetySettings": [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE"
                    }
                ]
            }
            
            print(f"🔄 Attempt {i+1}/{len(models)}: Trying model {model}")
            
            # Shorter timeout for first attempts, longer for last
            timeout = 30 if i < len(models) - 1 else 60
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            
            # Check for rate limiting
            if response.status_code == 429:
                print(f"⚠️ Rate limit hit on {model}")
                if i < len(models) - 1:
                    time.sleep(2)  # Wait before trying next model
                    continue
                else:
                    return jsonify({
                        'error': 'API rate limit exceeded. Please try again in a few seconds.',
                        'retry': True
                    }), 429
            
            # Check for other errors
            if response.status_code != 200:
                print(f"❌ Error from {model}: {response.status_code}")
                print(f"Response: {response.text[:500]}")
                if i < len(models) - 1:
                    continue  # Try next model
                else:
                    return jsonify({
                        'error': f'AI service returned error: {response.status_code}',
                        'details': response.text[:200]
                    }), 500
            
            result = response.json()
            
            # Validate response structure
            if 'candidates' not in result:
                print(f"❌ Invalid response structure from {model}")
                print(f"Response: {result}")
                if i < len(models) - 1:
                    continue
                else:
                    return jsonify({
                        'error': 'AI returned invalid response format',
                        'details': str(result)[:200]
                    }), 500
            
            candidates = result.get('candidates', [])
            if not candidates:
                print(f"❌ No candidates in response from {model}")
                if i < len(models) - 1:
                    continue
                else:
                    return jsonify({
                        'error': 'AI returned no content. Try again.',
                        'retry': True
                    }), 500
            
            # Extract text from first candidate
            candidate = candidates[0]
            content = candidate.get('content', {})
            parts = content.get('parts', [])
            
            if not parts or 'text' not in parts[0]:
                print(f"❌ No text in parts from {model}")
                if i < len(models) - 1:
                    continue
                else:
                    return jsonify({
                        'error': 'AI returned no text content',
                        'retry': True
                    }), 500
            
            bid_text = parts[0]['text'].strip()
            
            if not bid_text:
                print(f"❌ Empty bid text from {model}")
                if i < len(models) - 1:
                    continue
                else:
                    return jsonify({
                        'error': 'AI returned empty bid',
                        'retry': True
                    }), 500
            
            print(f"✅ Successfully generated bid using {model}")
            print(f"📊 Bid length: {len(bid_text)} characters")
            
            return jsonify({
                'bid': bid_text,
                'model_used': model,
                'success': True
            })
            
        except requests.exceptions.Timeout:
            print(f"⏱️ Timeout with {model}")
            if i < len(models) - 1:
                continue
            else:
                return jsonify({
                    'error': 'Request timed out. Please try again.',
                    'retry': True
                }), 504
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request exception with {model}: {str(e)}")
            if i < len(models) - 1:
                continue
            else:
                return jsonify({
                    'error': f'Network error: {str(e)}',
                    'retry': True
                }), 500
                
        except Exception as e:
            print(f"❌ Unexpected error with {model}: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            if i < len(models) - 1:
                continue
            else:
                return jsonify({
                    'error': f'Unexpected error: {str(e)}',
                    'retry': True
                }), 500
    
    # If all models failed
    return jsonify({
        'error': 'All AI models failed. Please try again later.',
        'retry': True
    }), 500


@app.route('/generate_graphics', methods=['POST'])
def generate_graphics_bid():
    """Generate a static graphics bid with project details."""
    try:
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

        return jsonify({
            'bid': graphics_bid,
            'success': True
        })
    except Exception as e:
        print(f"Error in generate_graphics: {str(e)}")
        return jsonify({
            'error': 'Failed to generate graphics bid',
            'details': str(e)
        }), 500
    
# profile route
@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    """
    Get all available freelancer profiles.
    This endpoint fetches profiles from Freelancer API or returns default profiles.
    """
    HEADERS = {
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Freelancer-OAuth-V1": PROD_TOKEN
    }
    
    try:
        # Try to fetch profiles from Freelancer API
        url = "https://www.freelancer.com/api/users/0.1/profiles/"
        response = requests.get(url, headers=HEADERS, timeout=15)
        print('response profile', response)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 'success':
                profiles_data = result.get('result', {}).get('profiles', {})
                
                # Format profiles for frontend
                profiles = []
                for profile_id, profile_info in profiles_data.items():
                    profiles.append({
                        'id': int(profile_id),
                        'name': profile_info.get('name', 'General'),
                        'description': profile_info.get('description', '')
                    })
                
                return jsonify({
                    'success': True,
                    'name':'api profiles',
                    'profiles': profiles
                })
    except Exception as e:
        print(f"Error fetching profiles from API: {e}")
    
    # Return default profiles if API fails
    default_profiles = [
        {
            'id': 0,
            'name': 'General',
            'description': 'General freelancing profile'
        },
        {
            'id': 1,
            'name': 'SEO, Digital Marketing',
            'description': 'SEO and digital marketing services'
        },
        {
            'id': 2,
            'name': 'Logo & Illustration',
            'description': 'Logo design and illustration services'
        },
        {
            'id': 3,
            'name': 'Graphics & Print Media',
            'description': 'Graphics and print design services'
        },
        {
            'id': 4,
            'name': 'PowerPoint & Presentation',
            'description': 'Presentation design services'
        }
    ]
    
    return jsonify({
        'success': True,
        'name':'default profiles',
        'profiles': default_profiles
    })

@app.route('/place_bid', methods=['POST'])
def place_bid():
    """
    Places a bid and stores it in MongoDB with user information and profile.
    """
    data = request.get_json() or {}

    # Project details
    project_id = data.get('project_id')
    bid_text = data.get('bid')
    amount = float(data.get('amount', 50))
    period = int(data.get('period', 7))
    project_title = data.get('project_title') or "Untitled"
    project_url = data.get('project_url') or "#"

    # User details
    user_id = data.get('user_id')
    user_email = data.get('user_email')
    role = data.get('role')

    # Profile details
    profile_id = data.get('profile_id', 0)  
    profile_name = data.get('profile_name', 'General')

    # Validation
    if not project_id or not bid_text:
        return jsonify({'error': 'Project ID and bid text required'}), 400
    
    if not user_id or not user_email:
        return jsonify({'error': 'User information required'}), 400

    # Duplicate Check
    existing_bid = bids_collection.find_one({
        "user_id": user_id,
        "project_id": project_id
    })
    
    if existing_bid:
        return jsonify({
            'success': False,
            'message': 'You have already bid on this project'
        }), 409

    # Try to get bidder ID from Freelancer API
    bidder_id = None
    try:
        url_self = "https://www.freelancer.com/api/users/0.1/self/"
        headers = {"Authorization": f"Bearer {PROD_TOKEN}"}
        response = requests.get(url_self, headers=headers, timeout=30)
        response.raise_for_status()
        bidder_id = response.json().get("result", {}).get("id")
    except Exception:
        bidder_id = None

    # Prepare bid payload for Freelancer API with profile
    bid_payload = {
        "project_id": project_id,
        "bidder_id": bidder_id,
        "amount": amount,
        "period": period,
        "milestone_percentage": 100,
        "description": bid_text,
        "profile_id": profile_id
    }

    headers_post = {
        "Authorization": f"Bearer {PROD_TOKEN}",
        "Content-Type": "application/json"
    }

    # Submit to Freelancer API
    try:
        r = requests.post(
            "https://www.freelancer.com/api/projects/0.1/bids/",
            headers=headers_post,
            json=bid_payload,
            timeout=30
        )
        r.raise_for_status()
    except Exception as err:
        return jsonify({
            "success": False,
            "message": f"❌ Failed to submit bid to Freelancer API: {str(err)}",
            "error": str(err)
        }), 500
    
    # Get IST timezone
    IST = timezone(timedelta(hours=5, minutes=30))
    current_ist = datetime.now(IST).replace(tzinfo=None)
    
    # Store bid in MongoDB with profile information and default bid_status
    bid_data = {
        "user_id": user_id,
        "user_email": user_email,
        "role": role,
        "username": user_email.split('@')[0],
        "title": project_title,
        "link": project_url,
        "project_id": project_id,
        "amount": amount,
        "period": period,
        "bid_text": bid_text,
        "profile_id": profile_id,
        "profile_name": profile_name,
        "status": "sent",
        "bid_status": "pending",  # Default status: pending (not seen yet)
        "created_at": current_ist,
        "updated_at": current_ist
    }
    
    result = bids_collection.insert_one(bid_data)

    return jsonify({
        "success": True,
        "message": f"✅ Bid sent successfully using {profile_name} profile!",
        "bid_id": str(result.inserted_id),
        "external": r.json()
    }), 200


@app.route('/api/bids/update-status', methods=['POST'])
def update_bid_status():
    """
    Update bid status with new valid statuses: pending, bid_seen, response_received, awarded
    """
    data = request.json
    bid_id = data.get("bid_id")
    new_status = data.get("bid_status")

    if not bid_id or not new_status:
        return jsonify({"success": False, "message": "Missing fields"}), 400

    # Updated valid statuses
    valid_status = ["pending", "bid_seen", "response_received", "awarded"]

    if new_status not in valid_status:
        return jsonify({"success": False, "message": "Invalid status"}), 400

    # Get IST timezone for updated_at
    IST = timezone(timedelta(hours=5, minutes=30))
    current_ist = datetime.now(IST).replace(tzinfo=None)

    result = bids_collection.update_one(
        {"_id": ObjectId(bid_id)},
        {
            "$set": {
                "bid_status": new_status,
                "updated_at": current_ist
            }
        }
    )

    if result.modified_count == 0:
        return jsonify({"success": False, "message": "Bid not found or no changes made"}), 404

    return jsonify({
        "success": True, 
        "message": f"Bid status updated to {new_status}"
    })


@app.route('/api/bids/tracker', methods=['GET'])
def get_bid_tracker():
    """
    Get bid tracker data. Expects user_id and role as query parameters.
    For admin: returns all users' bids grouped by user and date with status counts
    For user: returns only their bids grouped by date with status counts
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
        # Get all bids for all users with status counts
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
                            'bid_status': '$bid_status',
                            'bid_text': '$bid_text',
                            'status': '$status',
                            'created_at': '$created_at'
                        }
                    },
                    'total_count': {'$sum': 1},
                    'total_amount': {'$sum': '$amount'},
                    # Count by status
                    'pending_count': {
                        '$sum': {
                            '$cond': [{'$eq': ['$bid_status', 'pending']}, 1, 0]
                        }
                    },
                    'bid_seen_count': {
                        '$sum': {
                            '$cond': [{'$eq': ['$bid_status', 'bid_seen']}, 1, 0]
                        }
                    },
                    'response_received_count': {
                        '$sum': {
                            '$cond': [{'$eq': ['$bid_status', 'response_received']}, 1, 0]
                        }
                    },
                    'awarded_count': {
                        '$sum': {
                            '$cond': [{'$eq': ['$bid_status', 'awarded']}, 1, 0]
                        }
                    }
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
                    'dates': {},
                    'total_bids': 0,
                    'total_amount': 0,
                    'status_counts': {
                        'pending': 0,
                        'bid_seen': 0,
                        'response_received': 0,
                        'awarded': 0
                    }
                }
            
            users_data[uid]['dates'][date] = {
                'date': date,
                'bids': item['bids'],
                'total_count': item['total_count'],
                'total_amount': item['total_amount'],
                'status_counts': {
                    'pending': item.get('pending_count', 0),
                    'bid_seen': item.get('bid_seen_count', 0),
                    'response_received': item.get('response_received_count', 0),
                    'awarded': item.get('awarded_count', 0)
                }
            }
            
            # Aggregate user totals
            users_data[uid]['total_bids'] += item['total_count']
            users_data[uid]['total_amount'] += item['total_amount']
            users_data[uid]['status_counts']['pending'] += item.get('pending_count', 0)
            users_data[uid]['status_counts']['bid_seen'] += item.get('bid_seen_count', 0)
            users_data[uid]['status_counts']['response_received'] += item.get('response_received_count', 0)
            users_data[uid]['status_counts']['awarded'] += item.get('awarded_count', 0)
        
        return jsonify({
            'success': True,
            'year': year,
            'month': month,
            'is_admin': True,
            'users': list(users_data.values())
        })
    
    else:
        # Get only current user's bids with status counts
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
                            'bid_status': '$bid_status',
                            'bid_text': '$bid_text',
                            'status': '$status',
                            'created_at': '$created_at'
                        }
                    },
                    'total_count': {'$sum': 1},
                    'total_amount': {'$sum': '$amount'},
                    # Count by status
                    'pending_count': {
                        '$sum': {
                            '$cond': [{'$eq': ['$bid_status', 'pending']}, 1, 0]
                        }
                    },
                    'bid_seen_count': {
                        '$sum': {
                            '$cond': [{'$eq': ['$bid_status', 'bid_seen']}, 1, 0]
                        }
                    },
                    'response_received_count': {
                        '$sum': {
                            '$cond': [{'$eq': ['$bid_status', 'response_received']}, 1, 0]
                        }
                    },
                    'awarded_count': {
                        '$sum': {
                            '$cond': [{'$eq': ['$bid_status', 'awarded']}, 1, 0]
                        }
                    }
                }
            },
            {
                '$sort': {'_id': -1}
            }
        ]
        
        results = list(bids_collection.aggregate(pipeline))
        
        dates_data = {}
        month_totals = {
            'total_bids': 0,
            'total_amount': 0,
            'status_counts': {
                'pending': 0,
                'bid_seen': 0,
                'response_received': 0,
                'awarded': 0
            }
        }
        
        for item in results:
            date = item['_id']
            dates_data[date] = {
                'date': date,
                'bids': item['bids'],
                'total_count': item['total_count'],
                'total_amount': item['total_amount'],
                'status_counts': {
                    'pending': item.get('pending_count', 0),
                    'bid_seen': item.get('bid_seen_count', 0),
                    'response_received': item.get('response_received_count', 0),
                    'awarded': item.get('awarded_count', 0)
                }
            }
            
            # Aggregate month totals
            month_totals['total_bids'] += item['total_count']
            month_totals['total_amount'] += item['total_amount']
            month_totals['status_counts']['pending'] += item.get('pending_count', 0)
            month_totals['status_counts']['bid_seen'] += item.get('bid_seen_count', 0)
            month_totals['status_counts']['response_received'] += item.get('response_received_count', 0)
            month_totals['status_counts']['awarded'] += item.get('awarded_count', 0)
        
        return jsonify({
            'success': True,
            'year': year,
            'month': month,
            'is_admin': False,
            'dates': dates_data,
            'month_totals': month_totals
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
