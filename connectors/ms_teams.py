import msal
import requests

# 1. REPLACE THIS with your actual company email domain (e.g., "accenture.com")
COMPANY_DOMAIN = "accenture.com" 

AUTHORITY = f"https://login.microsoftonline.com/{COMPANY_DOMAIN}"

# Use the official Microsoft Azure CLI Client ID (highly reliable for device flow)
AZURE_CLI_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"

# Basic permissions to access your profile
SCOPES = ["User.Read"]

print(f"Starting authentication flow for tenant: {COMPANY_DOMAIN}...")

# Initialize MSAL targeting your company's directory explicitly
app = msal.PublicClientApplication(AZURE_CLI_CLIENT_ID, authority=AUTHORITY)

flow = app.initiate_device_flow(scopes=SCOPES)

if "message" in flow:
    print("\n" + "="*60)
    print(flow["message"])
    print("="*60 + "\n")
    
    print("Waiting for your approval via browser & phone Authenticator...")
    result = app.acquire_token_by_device_flow(flow)
    
    if "access_token" in result:
        print("\n🎉 Login Successful!")
        token = result["access_token"]
        
        headers = {"Authorization": f"Bearer {token}"}
        user_profile = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers).json()
        print(f"Connected to: {user_profile.get('displayName')}")
    else:
        print("\n❌ Login failed:", result.get("error_description"))
else:
    print("Could not initiate device flow:", flow.get("error_description"))