from app import app, db, User
from werkzeug.security import generate_password_hash

def create_admin_user():
    try:
        with app.app_context():
            # Check if admin user already exists
            admin = User.query.filter_by(username="admin").first()
            if admin is None:
                admin = User(
                    username="admin",
                    email="admin@example.com",
                    name="Administrator",
                    is_admin=True
                )
                admin.set_password("admin123")
                db.session.add(admin)
                db.session.commit()
                print("Admin user created successfully")
            else:
                print("Admin user already exists")
    except Exception as e:
        print(f"Error creating admin user: {e}")

if __name__ == '__main__':
    create_admin_user() 