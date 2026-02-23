import os
import sys

# Add current directory to path if needed for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    try:
        from database import SessionLocal
        from models import ConfigStorage
        from auth import get_password_hash
        
        db = SessionLocal()
        try:
            config = db.query(ConfigStorage).filter(ConfigStorage.key == "admin_password").first()
            if not config:
                config = ConfigStorage(key="admin_password", value=get_password_hash("admin123"))
                db.add(config)
            else:
                config.value = get_password_hash("admin123")
            db.commit()
            print("====================================================")
            print("🚀 SUCCESS: Admin password has been reset to 'admin123'")
            print("Please login to the Web Panel and change it immediately.")
            print("====================================================")
        except Exception as e:
            print(f"Error touching database: {e}")
        finally:
            db.close()
    except ImportError as e:
        print(f"Could not load necessary modules: {e}")
        print("Make sure you are running this script inside the project virtual environment (venv).")

if __name__ == "__main__":
    print("Resetting admin password...")
    main()
