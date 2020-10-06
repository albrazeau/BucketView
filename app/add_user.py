from main import db, app
from db import User
from email_validator import validate_email
import sys

if __name__ == "__main__":
    email = validate_email(sys.argv[1]).email
    password = sys.argv[2]

    input(
        f"Do you wish to create a new user with the email: {email} and the password: {password}?"
        "\nPress Enter to continue, or CTRL+C to quit."
    )

    print("Creating user...")

    with app.app_context():
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

    print(f"Successfully created user: {email} with the password: {password}")
