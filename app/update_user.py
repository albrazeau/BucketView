from main import db, app
from db import User
from email_validator import validate_email
import sys

if __name__ == "__main__":
    email = validate_email(sys.argv[1]).email
    password = sys.argv[2]

    input(f"Do you wish to create a update the password of: {email}?" "\nPress Enter to continue, or CTRL+C to quit.")

    print("Updating password...")

    with app.app_context():
        user = User.query.get(email)
        user.set_password(password)
        db.session.commit()

    print(f"Successfully updated user: {email} with the password: {password}")
