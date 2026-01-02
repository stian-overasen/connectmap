"""
Setup script to generate OAuth tokens for Garmin Connect.
Run this once to get your OAuth tokens, then use them in the main app.
"""

import os

from dotenv import load_dotenv
from garminconnect import Garmin

load_dotenv()


def setup_oauth():
    """Generate OAuth tokens by logging in with email/password"""
    print("Garmin Connect OAuth Setup")
    print("=" * 50)

    # Get credentials
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    if not email or not password:
        email = input("Enter your Garmin Connect email: ")
        password = input("Enter your Garmin Connect password: ")

    try:
        print("\nLogging in to Garmin Connect...")
        client = Garmin(email, password)
        client.login()

        print("Login successful!")
        print("\nRetrieving OAuth tokens...")

        # Get the OAuth tokens from the session
        # Dump the tokens to dict format that can be serialized
        oauth1_token = client.garth.dumps()

        print("\n" + "=" * 50)
        print("OAuth tokens generated successfully!")
        print("=" * 50)
        print("\nAdd these to your .env file:")
        print(f"\nGARMIN_SESSION={oauth1_token}")
        print("\n" + "=" * 50)
        print("\nYou can now remove GARMIN_EMAIL and GARMIN_PASSWORD")
        print("from your .env file for better security.")
        print("=" * 50)

        # Optionally save to a file
        save = input("\nSave tokens to oauth_tokens.txt? (y/n): ")
        if save.lower() == "y":
            with open("oauth_tokens.txt", "w") as f:
                f.write("# Add these to your .env file:\n\n")
                f.write(f"GARMIN_SESSION={oauth1_token}\n")
            print("Tokens saved to oauth_tokens.txt")

        client.logout()

    except Exception as e:
        print(f"\nError: {e}")
        print("\nPlease check your credentials and try again.")


if __name__ == "__main__":
    setup_oauth()
