import mysql.connector

def test_connection():
    try:
        # Try to connect to XAMPP MySQL
        connection = mysql.connector.connect(
            host="localhost",
            port=3306,
            user="root",
            password=""
        )
        
        if connection.is_connected():
            print("Successfully connected to MySQL!")
            
            # Try to create database
            cursor = connection.cursor()
            cursor.execute("CREATE DATABASE IF NOT EXISTS anime_educational")
            print("Database 'anime_educational' created or already exists")
            
            cursor.close()
            connection.close()
            print("Connection closed")
            
    except mysql.connector.Error as e:
        print(f"Error connecting to MySQL: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    test_connection() 