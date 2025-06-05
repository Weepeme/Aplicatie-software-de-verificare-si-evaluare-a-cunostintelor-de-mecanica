import os
from flask import Flask
from pymongo import MongoClient

def create_app():
    # Creează o instanță Flask
    app = Flask(__name__)

    # Creează o conexiune către MongoDB Atlas folosind variabila de mediu
    client = MongoClient(os.environ["MONGO_URI"])

    # Selectează baza de date
    db = client["questions_for_app"]

    # Selectează colecțiile din baza de date
    app.config["QUESTIONS_COLLECTION"] = db["Questions"]
    app.config["LEADERBOARD_COLLECTION"] = db["leaderboard"]

    # Resetează leaderboard-ul la pornirea aplicației - doar pentru test!
    db["leaderboard"].delete_many({})

    # Înregistrează Blueprint-ul pentru rutare
    from .routes import bp
    app.register_blueprint(bp)

    return app
