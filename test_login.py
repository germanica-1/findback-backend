
import getpass
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
supabase_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]

email = input("Test student's email: ").strip()
password = getpass.getpass("Test student's password: ")

response = httpx.post(
    f"{supabase_url}/auth/v1/token",
    params={"grant_type": "password"},
    headers={"apikey": supabase_key},
    json={"email": email, "password": password},
    timeout=15,
)


if response.is_success:
    data = response.json()
    access_token = data["access_token"]

    verify = httpx.get(
        f"{supabase_url}/auth/v1/user",
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=15,
    )

    print("Login status:", response.status_code)
    print("Token verification status:", verify.status_code)

    if verify.is_success:
        print("SUCCESS: Supabase accepts the access token.")
        print("User:", verify.json().get("email"))
    else:
        print("Token verification failed:", verify.text)
else:
    print("Login failed:", response.status_code)
    print(response.text)
    print("\nLogin failed:", response.status_code)
    print(response.text)

