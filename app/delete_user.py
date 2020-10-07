from main import db, app
from db import User
from email_validator import validate_email
import sys

if __name__ == "__main__":
    email = validate_email(sys.argv[1]).email

    input(f"Do you wish to delete the following user: {email}?\nPress Enter to continue, or CTRL+C to quit.")

    print("Deleting user...")

    with app.app_context():
        User.query.filter(User.email == email).delete()
        db.session.commit()

    print(f"Successfully deleted user: {email}")
