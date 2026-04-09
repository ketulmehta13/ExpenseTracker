import urllib.request
import urllib.error
import json
import uuid
import sys

BASE_URL = "http://127.0.0.1:8000/api"

def print_result(step, status_code, output):
    print(f"\n--- {step} ---")
    print(f"Status Code: {status_code}")
    print(f"Response: {output}")

def make_request(url, payload=None, headers=None):
    if headers is None:
        headers = {}
    
    data = None
    if payload:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(url, data=data, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
            body = response.read().decode('utf-8')
            try:
                body_json = json.loads(body)
                return status, body_json
            except json.JSONDecodeError:
                return status, body
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode('utf-8')
        try:
            body_json = json.loads(body)
            return status, body_json
        except json.JSONDecodeError:
            return status, body
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}")
        sys.exit(1)

def test_auth():
    print("Testing Authentication Locally...")
    
    username = f"testuser_{uuid.uuid4().hex[:6]}"
    password = "testpassword123!"
    email = f"{username}@example.com"
    
    # 1. Register a new user
    register_url = f"{BASE_URL}/auth/register/"
    payload = {"username": username, "email": email, "password": password}
    
    print(f"\n[Step 1] Registering user: {username}")
    status, body = make_request(register_url, payload)
    print_result("Register", status, body)
    
    if status not in [200, 201]:
        print("Registration failed. Continuing to login anyway on a test user if possible...")
    
    # 2. Login
    login_url = f"{BASE_URL}/auth/login/"
    login_payload = {"username": username, "password": password}
    
    print(f"\n[Step 2] Logging in user: {username}")
    login_status, login_body = make_request(login_url, login_payload)
    print_result("Login", login_status, login_body)
    
    if login_status == 200:
        tokens = login_body
        print("\nLogin Successful!")
        print(f"Access Token: {tokens.get('access')[:20]}...")
        print(f"Refresh Token: {tokens.get('refresh')[:20]}...")
    else:
        print("\nLogin Failed!")
        sys.exit(1)

    # 3. Test Protected Route (Profile)
    profile_url = f"{BASE_URL}/auth/me/"
    headers = {"Authorization": f"Bearer {tokens.get('access')}"}
    
    print(f"\n[Step 3] Fetching protected route (Profile)")
    prof_status, prof_body = make_request(profile_url, headers=headers)
    print_result("Profile Fetch", prof_status, prof_body)

if __name__ == "__main__":
    test_auth()
