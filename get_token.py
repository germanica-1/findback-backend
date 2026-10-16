import getpass
import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_PUBLISHABLE_KEY"]

email = input("Test student email: ")
password = input("Test student password: ")

supabase = create_client(url, key)
result = supabase.auth.sign_in_with_password(
    {"email": email, "password": password}
)

print("\nSign-in successful!")
print("User ID:", result.user.id)
print("\nAccess token (copy this into Swagger):")
print(result.session.access_token)
