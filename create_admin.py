
import database


def main():
    print("=" * 45)
    print(" CAMPUSCONNECT - ADMIN ACCOUNT SETUP")
    print("=" * 45)

    if database.admin_exists():
        print("\nAn admin account already exists.")
        print("This setup script will not create another account.")
        return

    username = input("\nEnter admin username: ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    password = input("Enter admin password (minimum 8 characters): ")
    confirm_password = input("Confirm admin password: ")

    if len(password) < 8:
        print("Password must contain at least 8 characters.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    created = database.create_admin(username, password)

    if created:
        print("\nAdmin account created successfully!")
        print("Username:", username)
        print("You can now log in using the Admin Login tab.")
    else:
        print("\nCould not create admin account.")


if __name__ == "__main__":
    main()
