from flask_login import LoginManager
from app.models import User
from bson.objectid import ObjectId
import os
from flask import Flask
from pymongo import MongoClient
from flask_login import LoginManager

def create_app():
    # Creăm o instanță Flask
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'un_secret_puternic_aici'  # Secret key necesar pentru sesiuni și cookie-uri securizate
    
    login_manager = LoginManager()  # Inițializăm managerul de autentificare
    login_manager.init_app(app)  # Îl legăm de aplicația Flask
    login_manager.login_view = "routes.login"  # Dacă utilizatorul nu este autentificat, îl redirecționăm către ruta 'login'
   
    # Funcția care încarcă utilizatorul pentru Flask-Login pe baza user_id din sesiune
    @login_manager.user_loader
    def load_user(user_id):
        users_collection = app.config.get('USERS_COLLECTION')  # Accesăm colecția de utilizatori
        user_data = users_collection.find_one({'_id': ObjectId(user_id)})  # Căutăm utilizatorul după ID-ul MongoDB
        if user_data:
            return User(user_data)  # Returnăm un obiect User creat cu datele din MongoDB
        return None  # Dacă nu există utilizator, returnăm None
    
    # Creăm conexiunea la MongoDB folosind variabila de mediu MONGO_URI
    client = MongoClient(os.environ["MONGO_URI"])
    db = client["questions_for_app"]  # Selectăm baza de date
    
    # Setăm colecțiile în configurarea Flask pentru acces ușor în alte părți ale aplicației
    app.config["QUESTIONS_COLLECTION"] = db["Questions"]
    app.config["LEADERBOARD_COLLECTION"] = db["leaderboard"]
    app.config["USERS_COLLECTION"] = db["users"]
    app.config["TESTS_COLLECTION"] = db["Tests"]

    from .routes import bp  # Importăm blueprint-ul cu rutele aplicației
    app.register_blueprint(bp)  # Înregistrăm blueprint-ul la aplicație

    return app  # Returnăm aplicația Flask configurată
