from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import json
import sys
import os

# Add the parent directory to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import app configuration
from app import app, db, User

def run_migration():
    """Add recovery_email, profile_frame, and unlocked_frames columns to User table"""
    
    with app.app_context():
        try:
            # Check if columns exist in User table
            inspector = db.inspect(db.engine)
            columns = inspector.get_columns('user')
            column_names = [c['name'] for c in columns]
            
            # Add recovery_email column if it doesn't exist
            if 'recovery_email' not in column_names:
                print("Adding recovery_email column to User table...")
                db.session.execute(text('ALTER TABLE user ADD COLUMN recovery_email VARCHAR(120)'))
                print("Added recovery_email column successfully.")
            else:
                print("recovery_email column already exists.")
            
            # Add profile_frame column if it doesn't exist
            if 'profile_frame' not in column_names:
                print("Adding profile_frame column to User table...")
                db.session.execute(text("ALTER TABLE user ADD COLUMN profile_frame VARCHAR(100) DEFAULT 'default'"))
                print("Added profile_frame column successfully.")
            else:
                print("profile_frame column already exists.")
            
            # Add unlocked_frames column if it doesn't exist
            if 'unlocked_frames' not in column_names:
                print("Adding unlocked_frames column to User table...")
                db.session.execute(text("ALTER TABLE user ADD COLUMN unlocked_frames TEXT DEFAULT '[\"default\"]'"))
                print("Added unlocked_frames column successfully.")
            else:
                print("unlocked_frames column already exists.")
                
            # Commit the changes
            db.session.commit()
            print("Migration completed successfully!")
            
        except Exception as e:
            print(f"Migration failed: {e}")
            db.session.rollback()

if __name__ == "__main__":
    run_migration() 