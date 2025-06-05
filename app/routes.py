from flask import Blueprint, render_template, current_app, jsonify, request, redirect, url_for
import random
from bson.objectid import ObjectId  # Import pentru conversia _id
# Creează un Blueprint pentru definirea rutelor
bp = Blueprint("routes", __name__)
# Ruta principală care returnează pagina de start
@bp.route("/")
def home():
    return render_template("home.html")
# Ruta pentru generarea și afișarea testului
@bp.route("/quiz", methods=["GET", "POST"])
def quiz():
     # Accesează colecția din config-ul aplicației
    questions_collection = current_app.config.get("QUESTIONS_COLLECTION")
# Verifică dacă colecția este disponibilă
    if questions_collection is None:
        return "Error: QUESTIONS_COLLECTION not found in config", 500

    if request.method == "POST":
        # Procesare răspunsuri și salvare scor
        user_name = request.form.get("user_name")  # Preluăm numele utilizatorului
        user_answers = request.form.to_dict(flat=True)

        correct_answers = 0
        total_questions = 0

        for key, user_answer in user_answers.items():
            if key.startswith("question_"):  # Filtrăm doar întrebările
                question_id = key.split("_")[1]  # Extragem ID-ul întrebării

                try:
                    question = questions_collection.find_one({"_id": ObjectId(question_id)})
                except:
                    continue  # Ignorăm erorile de conversie

                if question and user_answer.strip() == question["answer"].strip():
                    correct_answers += 1
                
                total_questions += 1

        # Verificăm colecția de clasament
        leaderboard_collection = current_app.config.get("LEADERBOARD_COLLECTION")
        if leaderboard_collection is None:
            return "Error: LEADERBOARD_COLLECTION not found in config", 500

        # Salvare scor în clasament
        leaderboard_collection.insert_one({
            "name": user_name,
            "score": correct_answers
        })

        return redirect(url_for("routes.leaderboard"))

    # Selectare întrebări pentru test
    questions = list(questions_collection.find({}))
# Dacă nu sunt întrebări în DB, se afișează mesajul
    if len(questions) == 0:
        return "Nu există întrebări în baza de date."
# Domeniile definite în aplicație
    domains = ["Cinematica", "Dinamica", "Statica", "Mecanica clasica"]
    selected_questions = []
# Se selectează câte 3 întrebări din fiecare domeniu (dacă există suficiente)
    for domain in domains:
        domain_questions = list(questions_collection.find({"domain": domain}))
        if domain_questions:
            selected_questions.extend(random.sample(domain_questions, min(3, len(domain_questions))))

    return render_template("quiz.html", questions=selected_questions)
# Ruta pentru afișarea clasamentului
@bp.route("/leaderboard")
def leaderboard():
    leaderboard_collection = current_app.config.get("LEADERBOARD_COLLECTION")
    if leaderboard_collection is None:
        return "Error: LEADERBOARD_COLLECTION not found in config", 500

    top_scores = leaderboard_collection.find().sort("score", -1).limit(10)
    
    return render_template("leaderboard.html", scores=top_scores)
