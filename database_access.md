# Database Access Guide

This guide explains how to access and manage the database for the Anime Educational Chatbot.

## Database Configuration

The application uses MySQL by default with SQLite as a fallback. The configuration is in `app.py`:

```python
# Connection details
Host: localhost
Port: 3306
Username: root
Password: (empty)
Database: anime_educational
```

## Accessing the Database

### Method 1: Using MySQL Workbench (Recommended)

1. Download and install [MySQL Workbench](https://dev.mysql.com/downloads/workbench/)
2. Open MySQL Workbench and create a new connection with these settings:
   - Connection Name: Anime Educational
   - Hostname: localhost
   - Port: 3306
   - Username: root
   - Password: (leave empty)
3. Once connected, select the `anime_educational` database from the schema list
4. You can now browse tables, run queries, and manage your data

### Method 2: Using Command Line

1. Open your terminal/command prompt
2. Connect to MySQL:
   ```bash
   mysql -u root -h localhost -P 3306
   ```
3. Select the database:
   ```sql
   USE anime_educational;
   ```
4. Run SQL commands:
   ```sql
   -- View all users
   SELECT * FROM user;
   
   -- View chat history
   SELECT * FROM chat_message;
   ```

### Method 3: Using the Python Shell

You can access the database directly using the SQLAlchemy models:

1. Start the Python interpreter in the project directory:
   ```bash
   python
   ```
2. Import the necessary modules:
   ```python
   from app import db, User, ChatMessage
   
   # Fetch all users
   users = User.query.all()
   for user in users:
       print(f"User: {user.username}, Email: {user.email}")
   
   # Fetch chat history for a specific user
   user = User.query.filter_by(username="example_user").first()
   if user:
       chats = ChatMessage.query.filter_by(user_id=user.id).all()
       for chat in chats:
           print(f"Message: {chat.message}")
   ```

## Database Schema

The database has the following main tables:

1. `user` - Stores user information
   - id: Primary key
   - username: Unique username
   - email: User's email address
   - password_hash: Hashed password
   - name: User's full name
   - (additional user fields)

2. `chat_message` - Stores chat history
   - id: Primary key
   - user_id: Foreign key to user table
   - message: User's message
   - response: Bot's response
   - timestamp: When the message was sent

## Database Utilities

The application provides several utility scripts:

- `init_db.py`: Initialize the database
- `test_db.py`: Test database connection
- `create_admin.py`: Create an admin user

You can run these scripts with:
```bash
python init_db.py
python test_db.py
python create_admin.py
```

## Backup and Restore

### Backup Database

Using mysqldump:
```bash
mysqldump -u root anime_educational > backup.sql
```

### Restore Database

From a mysqldump file:
```bash
mysql -u root anime_educational < backup.sql
```

## Troubleshooting

1. **Connection Issue**: If you cannot connect to MySQL, verify that the MySQL service is running on your system.

2. **Authentication Error**: If you get an authentication error, double check that you're using the correct username and password.

3. **Database Not Found**: If the database doesn't exist, run `python init_db.py` to create it.

4. **Table Not Found**: If tables are missing, ensure you've run the application at least once so that SQLAlchemy creates all tables. 