from flask_login import LoginManager
from app.models import User
from bson.objectid import ObjectId
import os
from flask import Flask
from pymongo import MongoClient
from flask_login import LoginManager


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'un_secret_puternic_aici'
    login_manager = LoginManager()              
    login_manager.init_app(app)
    login_manager.login_view = "routes.login"  # ruta pentru login
   
    @login_manager.user_loader
    def load_user(user_id):
        users_collection = app.config.get('USERS_COLLECTION')
        user_data = users_collection.find_one({'_id': ObjectId(user_id)})
        if user_data:
            return User(user_data)
        return None
    
 
    client = MongoClient(os.environ["MONGO_URI"])
    # Selectează baza de date
    db = client["questions_for_app"]
    # Selectează colecția din baza de date
    app.config["QUESTIONS_COLLECTION"] = db["Questions"]
    # Selectează colecția leaderboard
    app.config["LEADERBOARD_COLLECTION"] = db["leaderboard"]
    app.config["USERS_COLLECTION"] = db["users"]
    app.config["TESTS_COLLECTION"] = db["Tests"]

    from .routes import bp
    # Înregistrează Blueprint-ul pentru rutare
    app.register_blueprint(bp)

    return app
