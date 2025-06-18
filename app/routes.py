from urllib.parse import quote
from datetime import datetime, timedelta
from .models import User
from functools import wraps
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from uuid import uuid4
from flask import make_response, flash, abort
from xhtml2pdf import pisa
from io import BytesIO
from flask import Blueprint, render_template, current_app, jsonify, request, redirect, url_for
import random
from bson.objectid import ObjectId

# Creăm un blueprint pentru rutele aplicației - pentru organizarea codului în module
bp = Blueprint("routes", __name__)

# Decorator pentru restricționarea accesului pe bază de rol (ex: profesor)
def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Verificăm dacă utilizatorul este autentificat și are rolul necesar
            if not current_user.is_authenticated or current_user.role != role:
                abort(403)  # Acces interzis, returnăm HTTP 403 Forbidden
            return f(*args, **kwargs)
        return wrapped
    return decorator

# Ruta principală, redirecționează către login
@bp.route('/')
def home():
    return redirect(url_for('routes.login'))

# Dashboard-ul profesorului - afișează studenții și permite generarea testelor
@bp.route('/professor_dashboard', methods=['GET', 'POST'])
@login_required
@role_required('profesor')
def professor_dashboard():
    # Obținem referințele la colecțiile MongoDB din configurația aplicației
    students_collection = current_app.config.get("STUDENTS_COLLECTION")
    questions_collection = current_app.config.get("QUESTIONS_COLLECTION")
    tests_collection = current_app.config.get("TESTS_COLLECTION")

    # Preluăm lista completă de studenți pentru dropdown
    students = list(students_collection.find())

    test_url = None
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        difficulty = request.form.get('difficulty')  # Ex: "grad 1", "grad 2", "grad 3"

        # Validare câmpuri obligatorii
        if not student_id or not difficulty:
            flash("Completează toate câmpurile!", "warning")
            return redirect(url_for('routes.professor_dashboard'))

        # Căutăm studentul după ID (convertim în ObjectId)
        student = students_collection.find_one({"_id": ObjectId(student_id)})
        if not student:
            flash("Studentul nu există!", "danger")
            return redirect(url_for('routes.professor_dashboard'))

        # Verificăm dacă studentul a terminat deja un test la acest grad
        existing_test = tests_collection.find_one({
            "student_id": student_id,
            "difficulty": difficulty,
            "completed": True
        })
        if existing_test:
            flash("Studentul a luat deja testul la acest grad.", "warning")
            return redirect(url_for('routes.professor_dashboard'))

        # Domeniile din care se aleg întrebări
        domains = ["Cinematica", "Dinamica", "Statica"]
        selected_questions = []

        # Colectăm ID-urile întrebărilor folosite deja pentru acest grad, pentru a evita duplicarea
        used_question_ids = set()
        for test in tests_collection.find({"difficulty": difficulty, "completed": True}):
            for q in test["questions"]:
                used_question_ids.add(q["_id"])

        # Pentru fiecare domeniu, alegem 4 întrebări noi, excluzând întrebările deja folosite
        for domain in domains:
            available_questions = list(questions_collection.find({
                "domain": domain,
                "difficulty": difficulty,
                "_id": {"$nin": list(used_question_ids)}
            }))

            # Dacă nu sunt suficiente întrebări disponibile, afișăm eroare
            if len(available_questions) < 4:
                flash(f"Nu sunt suficiente întrebări noi pentru domeniul {domain} la dificultatea {difficulty}.", "danger")
                return redirect(url_for('routes.professor_dashboard'))

            # Alegem aleator 4 întrebări din cele disponibile
            selected_questions += random.sample(available_questions, 4)

        # Amestecăm întrebările pentru diversitate
        random.shuffle(selected_questions)

        # Creăm un ID unic pentru test (string UUID)
        test_id = str(uuid4())

        # Construim documentul testului ce va fi inserat în DB
        test_doc = {
            "_id": test_id,
            "student_id": student_id,
            "student_name": f"{student['nume']} {student['prenume']}",
            "difficulty": difficulty,
            "questions": selected_questions,
            "answers": {},
            "score": None,
            "completed": False,
            "created_at": datetime.utcnow(),
            "completed_at": None,
            "expires_at": datetime.utcnow() + timedelta(minutes=10)  # Test valid 10 minute
        }
        # Inserăm testul în colecția Tests
        tests_collection.insert_one(test_doc)

        # Generăm URL extern pentru testul creat
        test_url = url_for('routes.take_test', test_id=test_id, _external=True)
        flash("Test creat cu succes!", "success")

    # La GET afișăm pagina profesorului cu lista studenților și eventual link-ul testului
    return render_template('professor_dashboard.html', students=students, test_url=test_url)

# Ruta care redirecționează către pagina quiz (testul efectiv) pe baza test_id
@bp.route('/take_test/<test_id>')
def take_test(test_id):
    # Redirecționează către /quiz cu parametrul test_id
    return redirect(url_for('routes.quiz', test_id=test_id))

# Ruta pentru test (quiz)
@bp.route('/quiz', methods=['GET', 'POST'])
def quiz():
    test_id = request.args.get('test_id')
    if not test_id:
        return "ID-ul testului lipsește.", 400

    tests_collection = current_app.config.get("TESTS_COLLECTION")

    # Căutăm testul după string _id
    test_doc = tests_collection.find_one({"_id": test_id})
    if not test_doc:
        return "Testul nu există.", 404

    # Calculăm timpul rămas până la expirare
    time_left = (test_doc['expires_at'] - datetime.utcnow()).total_seconds()
    if time_left < 0:
        time_left = 0

    # Dacă testul a fost deja finalizat, afișăm scorul și blocăm testul
    if test_doc.get('completed', False):
        return f"Testul este deja finalizat. Scor: {test_doc.get('score', 0)}/12."

    if request.method == "POST":
        # Preluăm răspunsurile trimise de student
        user_answers = request.form.to_dict(flat=True)
        answers = test_doc.get('answers', {})
        answers.update(user_answers)  # Actualizăm răspunsurile în DB

        # Calculăm scorul bazat pe răspunsurile corecte
        score = 0
        for q in test_doc['questions']:
            qid = str(q['_id'])
            if qid in answers and answers[qid].strip() == q['answer'].strip():
                score += 1

        # Verificăm dacă testul este complet finalizat
        completed = request.form.get('completed') == 'true'

        # Pregătim datele pentru actualizare în DB
        update_data = {
            "answers": answers,
            "score": score,
            "completed": completed,
            "completed_at": datetime.utcnow() if completed else None
        }
        tests_collection.update_one({"_id": test_id}, {"$set": update_data})

        # Dacă testul e complet finalizat, redirecționăm la clasamentul studentului
        if completed:
            return redirect(url_for('routes.leaderboard_student', student_name=test_doc['student_name']))
        else:
            # Dacă e submit parțial (ex timer expirat), răspunsurile se salvează temporar
            return "Răspunsuri salvate temporar", 200

    # La GET afișăm pagina quiz cu întrebările, numele studentului și timpul rămas
    return render_template(
        'quiz.html',
        questions=test_doc['questions'],
        user_name=test_doc['student_name'],
        test_id=test_id,
        time_left=int(time_left)
    )

# Clasamentul individual al unui student
@bp.route('/leaderboard/student/<student_name>')
def leaderboard_student(student_name):
    tests_collection = current_app.config.get("TESTS_COLLECTION")
    if tests_collection is None:
        return "Configurație colecție teste lipsă", 500

    # Preluăm toate testele studentului, inclusiv cele nefinalizate, ordonate descrescător după data creării
    tests_cursor = tests_collection.find({
        "student_name": student_name
    }).sort("created_at", -1)

    tests = list(tests_cursor)

    # Calculăm media scorurilor; dacă nu există scor, considerăm 0
    if not tests:
        average_score = 0
        average_grade = 0
    else:
        total_score = sum(test.get('score', 0) or 0 for test in tests)
        count = len(tests)
        average_score = total_score / count if count > 0 else 0
        average_grade = (average_score / 12) * 10

    # Afișăm pagina leaderboard_student.html cu datele calculate
    return render_template('leaderboard_student.html',
                           student_name=student_name,
                           tests=tests,
                           average_score=average_score,
                           average_grade=average_grade)

# Logout - încheie sesiunea utilizatorului curent
@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('routes.login'))

# Login - autentificare pentru profesor
@bp.route('/login', methods=['GET', 'POST'])
def login():
    # Dacă este deja autentificat, redirecționăm la dashboard-ul profesorului
    if current_user.is_authenticated:
        return redirect(url_for('routes.professor_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        users_collection = current_app.config.get('USERS_COLLECTION')
        user_dict = users_collection.find_one({'username': username})

        # Verificăm parola criptată
        if user_dict and check_password_hash(user_dict['password_hash'], password):
            user = User(user_dict)
            login_user(user)
            flash('Autentificare reușită!', 'success')
            return redirect(url_for('routes.professor_dashboard'))
        else:
            flash('Nume utilizator sau parolă incorecte!', 'danger')

    # Afișăm pagina de login
    return render_template('login.html')

# Clasamentul global pentru profesori
@bp.route('/leaderboard')
@login_required
@role_required('profesor')
def leaderboard():
    tests_collection = current_app.config.get("TESTS_COLLECTION")
    if tests_collection is None:
        return "Configurație colecție teste lipsă", 500

    # Agregăm testele finalizate și calculăm media scorurilor per student
    pipeline = [
        {"$match": {"completed": True, "score": {"$ne": None}}},
        {"$group": {
            "_id": "$student_name",
            "tests": {"$push": {
                "difficulty": "$difficulty",
                "completed_at": "$completed_at",
                "score": "$score"
            }},
            "average_score": {"$avg": "$score"}
        }},
        {"$sort": {"average_score": -1}}
    ]

    leaderboard_data = list(tests_collection.aggregate(pipeline))

    # Calculăm nota echivalentă și determinăm dificultatea maximă parcursă
    for entry in leaderboard_data:
        entry['average_grade'] = (entry['average_score'] / 12) * 10
        difficulties = [test['difficulty'].lower() for test in entry['tests']]
        if "grad 3" in difficulties:
            entry['max_difficulty'] = 'grad 3'
        elif "grad 2" in difficulties:
            entry['max_difficulty'] = 'grad 2'
        elif "grad 1" in difficulties:
            entry['max_difficulty'] = 'grad 1'
        else:
            entry['max_difficulty'] = 'N/A'

    # Mapăm culoarea pentru fiecare grad
    color_map = {
        "grad 1": "green",
        "grad 2": "yellow",
        "grad 3": "red"
    }
    for entry in leaderboard_data:
        entry['color'] = color_map.get(entry['max_difficulty'], "black")

    # Afișăm pagina leaderboard.html cu datele prelucrate
    return render_template('leaderboard.html', leaderboard=leaderboard_data)

# Generare PDF pentru punctajul global
@bp.route('/leaderboard/pdf')
@login_required
@role_required('profesor')
def leaderboard_pdf():
    tests_collection = current_app.config.get("TESTS_COLLECTION")
    if tests_collection is None:
        return "Configurație colecție teste lipsă", 500

    # Preluăm toate testele finalizate cu scor valid, sortate după student și dată
    tests_cursor = tests_collection.find({
        "completed": True,
        "score": {"$ne": None}
    }).sort([("student_name", 1), ("completed_at", -1)])

    tests = list(tests_cursor)

    # Grupăm testele pe studenți și calculăm mediile
    students = {}
    for test in tests:
        name = test['student_name']
        if name not in students:
            students[name] = {
                "tests": [],
                "total_score": 0,
                "count": 0
            }
        students[name]["tests"].append(test)
        students[name]["total_score"] += test['score']
        students[name]["count"] += 1

    for student in students.values():
        student["average_score"] = student["total_score"] / student["count"] if student["count"] > 0 else 0
        student["average_grade"] = (student["average_score"] / 12) * 10

    # Redăm template-ul PDF cu datele studenților
    rendered = render_template(
        'leaderboard_pdf.html',
        students=students
    )

    # Generăm PDF-ul folosind pisa (xhtml2pdf)
    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(rendered, dest=pdf)
    if pisa_status.err:
        return "Eroare la generarea PDF-ului", 500

    # Trimitem PDF-ul ca răspuns HTTP
    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=Punctaj_Global.pdf'
    return response

# Generare PDF pentru punctajul individual al unui student
@bp.route('/leaderboard/student/<student_name>/pdf')
def leaderboard_student_pdf(student_name):
    tests_collection = current_app.config.get("TESTS_COLLECTION")
    if tests_collection is None:
        return "Configurație colecție teste lipsă", 500

    # Preluăm testele finalizate ale studentului cu scor valid, ordonate descrescător după data completării
    tests_cursor = tests_collection.find({
        "student_name": student_name,
        "completed": True,
        "score": {"$ne": None}
    }).sort("completed_at", -1)

    tests = list(tests_cursor)

    total_score = sum(test['score'] for test in tests if test.get('score') is not None) if tests else 0
    count = len(tests)
    average_score = total_score / count if count > 0 else 0
    average_grade = (average_score / 12) * 10

    # Redăm template-ul PDF cu detaliile testelor și mediile
    rendered = render_template('leaderboard_student_pdf.html',
                               student_name=student_name,
                               tests=tests,
                               average_score=average_score,
                               average_grade=average_grade)
    
    # Generăm PDF-ul cu pisa
    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(rendered, dest=pdf)
    if pisa_status.err:
        return "Eroare la generarea PDF-ului", 500

    # Trimitem PDF-ul ca răspuns HTTP
    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Punctaj_{student_name}.pdf'
    return response
