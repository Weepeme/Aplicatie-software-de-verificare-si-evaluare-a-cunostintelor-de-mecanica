from flask import make_response
from xhtml2pdf import pisa
from io import BytesIO
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
    questions_collection = current_app.config.get("QUESTIONS_COLLECTION")
    if questions_collection is None:
        return "Error: QUESTIONS_COLLECTION not found in config", 500

    if request.method == "POST":
        user_name = request.form.get("user_name")
        difficulty = request.form.get("difficulty")
        # Detectăm dacă e inițiere quiz (nu există niciun question_ în form)
        has_answers = any(key.startswith("question_") for key in request.form.keys())

        if not has_answers:
            # Inițiere quiz: trimite 4x3 întrebări random
            domains = ["Cinematica", "Dinamica", "Statica"]
            selected_questions = []
            for domain in domains:
                questions = list(questions_collection.find({"domain": domain, "difficulty": difficulty}))
                if len(questions) < 4:
                    return f"Nu există suficiente întrebări la domeniul {domain}, dificultatea {difficulty}."
                selected_questions += random.sample(questions, 4)
            random.shuffle(selected_questions)
            # Trimite și user_name + difficulty la quiz.html
            return render_template("quiz.html", questions=selected_questions, user_name=user_name, difficulty=difficulty)
        else:
            # Submit răspunsuri la quiz
            user_answers = request.form.to_dict(flat=True)
            correct_answers = 0
            total_questions = 0
            for key, user_answer in user_answers.items():
                if key.startswith("question_"):
                    question_id = key.split("_")[1]
                    try:
                        question = questions_collection.find_one({"_id": ObjectId(question_id)})
                    except:
                        continue
                    if question and user_answer.strip() == question["answer"].strip():
                        correct_answers += 1
                    total_questions += 1
            leaderboard_collection = current_app.config.get("LEADERBOARD_COLLECTION")
            if leaderboard_collection is None:
                return "Error: LEADERBOARD_COLLECTION not found in config", 500
            leaderboard_collection.insert_one({
                "name": user_name,
                "score": correct_answers,
                "difficulty": difficulty
            })
            return redirect(url_for("routes.leaderboard"))

    # Dacă ajunge aici cu GET, redirect la home
    return redirect(url_for("routes.home"))


    # Dacă request-ul e GET (sau POST inițial cu dificultate), începem quiz-ul
    # Preia dificultatea selectată din query params sau formular
    difficulty = request.args.get("difficulty") or request.form.get("difficulty")
    if not difficulty:
        # Dacă nu s-a trimis dificultatea, redirect la home
        return redirect(url_for("routes.home"))

    # Definim lista domeniilor
    domains = ["Cinematica", "Dinamica", "Statica"]
    selected_questions = []  # Listă unde vom adăuga toate întrebările selectate

    # Pentru fiecare domeniu, extragem 4 întrebări random cu dificultatea aleasă
    for domain in domains:
        # Găsim toate întrebările din acel domeniu și cu dificultatea dorită
        questions = list(questions_collection.find({"domain": domain, "difficulty": difficulty}))
        if len(questions) < 4:
            # Dacă nu avem destule întrebări, returnăm mesaj de eroare explicit
            return f"Nu există suficiente întrebări la domeniul {domain}, dificultatea {difficulty}."
        # Alegem random 4 întrebări din listă (fără repetare)
        selected_questions += random.sample(questions, 4)

    # Amestecăm toate întrebările astfel încât să nu fie grupate pe domenii
    random.shuffle(selected_questions)

    # Trimitem lista de întrebări către template-ul de quiz
    return render_template("quiz.html", questions=selected_questions)

# Ruta pentru afișarea clasamentului
@bp.route("/leaderboard")
def leaderboard():
    leaderboard_collection = current_app.config.get("LEADERBOARD_COLLECTION")
    if leaderboard_collection is None:
        return "Error: LEADERBOARD_COLLECTION not found in config", 500
    scores = list(leaderboard_collection.find().sort("score", -1))
    return render_template("leaderboard.html", scores=scores)

@bp.route("/leaderboard/pdf")
def leaderboard_pdf():
    leaderboard_collection = current_app.config.get("LEADERBOARD_COLLECTION")
    if leaderboard_collection is None:
        return "Error: LEADERBOARD_COLLECTION not found in config", 500

    scores = list(leaderboard_collection.find().sort("score", -1))
    rendered = render_template("leaderboard_pdf.html", scores=scores)

    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(rendered, dest=pdf)
    if pisa_status.err:
        return "Eroare la generarea PDF-ului", 500

    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=Punctaj.pdf'
    return response