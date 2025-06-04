from app import app, db
import mysql.connector

def init_database():
    try:
        # Create database if it doesn't exist
        with mysql.connector.connect(
            host="localhost",
            user="root",
            password=""
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE DATABASE IF NOT EXISTS anime_educational")
                print("Database created or already exists")
        
        # Create tables
        with app.app_context():
            db.create_all()
            print("Tables created successfully")
            
    except Exception as e:
        print(f"Error initializing database: {e}")

if __name__ == '__main__':
    init_database() 