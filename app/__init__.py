import os
from flask import Flask
from pymongo import MongoClient

def create_app():
    # Creează o instanță Flask
    app = Flask(__name__)
   
 # Creează o conexiune către MongoDB Atlas folosind un connection string
    client = MongoClient("mongodb+srv://adriandumitru150:Rebelde150@cluster0.vkfbx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
    # Selectează baza de date
    db = client["questions_for_app"]
    # Selectează colecția din baza de date
    app.config["QUESTIONS_COLLECTION"] = db["Questions"]
    # Selectează colecția leaderboard
    app.config["LEADERBOARD_COLLECTION"] = db["leaderboard"]

    db["leaderboard"].delete_many({})

    from .routes import bp
    # Înregistrează Blueprint-ul pentru rutare
    app.register_blueprint(bp)

    return app