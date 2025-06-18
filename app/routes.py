from urllib.parse import quote
from datetime import datetime, timedelta
from .models import User
from functools import wraps
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from uuid import uuid4
from datetime import datetime, timedelta
from flask import make_response, flash, abort
from xhtml2pdf import pisa
from io import BytesIO
from flask import Blueprint, render_template, current_app, jsonify, request, redirect, url_for
import random
from bson.objectid import ObjectId

# Creăm un blueprint pentru rutele aplicației
bp = Blueprint("routes", __name__)

# Decorator pentru restricționarea accesului pe bază de rol
def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Verificăm dacă utilizatorul este autentificat și are rolul necesar
            if not current_user.is_authenticated or current_user.role != role:
                abort(403)  # Acces interzis
            return f(*args, **kwargs)
        return wrapped
    return decorator

# Ruta principală redirecționează către login indiferent de stare
@bp.route('/')
def home():
    return redirect(url_for('routes.login'))

# Dashboard-ul profesorului: aici poate genera teste pentru studenți
@bp.route('/professor_dashboard', methods=['GET', 'POST'])
@login_required
@role_required('profesor')
def professor_dashboard():
    students_collection = current_app.config.get("STUDENTS_COLLECTION")
    questions_collection = current_app.config.get("QUESTIONS_COLLECTION")
    tests_collection = current_app.config.get("TESTS_COLLECTION")

    students = list(students_collection.find())  # pentru dropdown

    test_url = None
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        difficulty = request.form.get('difficulty')  # "grad 1", "grad 2" sau "grad 3"

        if not student_id or not difficulty:
            flash("Completează toate câmpurile!", "warning")
            return redirect(url_for('routes.professor_dashboard'))

        # Obține studentul după ID
        student = students_collection.find_one({"_id": ObjectId(student_id)})
        if not student:
            flash("Studentul nu există!", "danger")
            return redirect(url_for('routes.professor_dashboard'))

        # Opțional: verifică dacă studentul a terminat deja testul la acest grad
        existing_test = tests_collection.find_one({
            "student_id": student_id,
            "difficulty": difficulty,
            "completed": True
        })
        if existing_test:
            flash("Studentul a luat deja testul la acest grad.", "warning")
            return redirect(url_for('routes.professor_dashboard'))

        domains = ["Cinematica", "Dinamica", "Statica"]
        selected_questions = []

        # Adună toate întrebările folosite deja la acest grad (dif) de alți studenți
        used_question_ids = set()
        for test in tests_collection.find({"difficulty": difficulty, "completed": True}):
            for q in test["questions"]:
                used_question_ids.add(q["_id"])

        # Alege câte 4 întrebări per domeniu, excluzând întrebările deja folosite
        for domain in domains:
            available_questions = list(questions_collection.find({
                "domain": domain,
                "difficulty": difficulty,
                "_id": {"$nin": list(used_question_ids)}
            }))

            if len(available_questions) < 4:
                flash(f"Nu sunt suficiente întrebări noi pentru domeniul {domain} la dificultatea {difficulty}.", "danger")
                return redirect(url_for('routes.professor_dashboard'))

            selected_questions += random.sample(available_questions, 4)

        random.shuffle(selected_questions)

        test_id = str(uuid4())
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
            "expires_at": datetime.utcnow() + timedelta(minutes=10)
        }
        tests_collection.insert_one(test_doc)

        test_url = url_for('routes.take_test', test_id=test_id, _external=True)
        flash("Test creat cu succes!", "success")

    return render_template('professor_dashboard.html', students=students, test_url=test_url)


# Ruta care redirecționează către pagina quiz cu testul
@bp.route('/take_test/<test_id>')
def take_test(test_id):
    # Redirecționăm către /quiz cu parametru test_id pentru afișarea testului
    return redirect(url_for('routes.quiz', test_id=test_id))

@bp.route('/quiz', methods=['GET', 'POST'])
def quiz():
    test_id = request.args.get('test_id')
    if not test_id:
        return "ID-ul testului lipsește.", 400

    tests_collection = current_app.config.get("TESTS_COLLECTION")

    # Căutăm testul după string _id (nu ObjectId)
    test_doc = tests_collection.find_one({"_id": test_id})
    if not test_doc:
        return "Testul nu există.", 404

    # Calculăm timpul rămas
    time_left = (test_doc['expires_at'] - datetime.utcnow()).total_seconds()
    if time_left < 0:
        time_left = 0

    # Dacă testul e finalizat, afișăm scorul
    if test_doc.get('completed', False):
        return f"Testul este deja finalizat. Scor: {test_doc.get('score', 0)}/12."

    if request.method == "POST":
        user_answers = request.form.to_dict(flat=True)
        answers = test_doc.get('answers', {})
        answers.update(user_answers)

        score = 0
        for q in test_doc['questions']:
            qid = str(q['_id'])
            if qid in answers and answers[qid].strip() == q['answer'].strip():
                score += 1

        completed = request.form.get('completed') == 'true'

        update_data = {
            "answers": answers,
            "score": score,
            "completed": completed,
            "completed_at": datetime.utcnow() if completed else None
        }
        tests_collection.update_one({"_id": test_id}, {"$set": update_data})

        if completed:
            return redirect(url_for('routes.leaderboard_student', student_name=test_doc['student_name']))
        else:
            return "Răspunsuri salvate temporar", 200

    # La GET afișăm pagina quiz
    return render_template(
        'quiz.html',
        questions=test_doc['questions'],
        user_name=test_doc['student_name'],
        test_id=test_id,
        time_left=int(time_left)
    )


# Punctaj individual al unui student (toate testele lui)
@bp.route('/leaderboard/student/<student_name>')
def leaderboard_student(student_name):
    tests_collection = current_app.config.get("TESTS_COLLECTION")
    if tests_collection is None:
        return "Configurație colecție teste lipsă", 500

    # Preluăm toate testele studentului, inclusiv cele nefinalizate
    tests_cursor = tests_collection.find({
        "student_name": student_name
    }).sort("created_at", -1)

    tests = list(tests_cursor)

    if not tests:
        average_score = 0
        average_grade = 0
    else:
        # Calculăm media scorurilor (dacă scorul nu există, considerăm 0)
        total_score = sum(test.get('score', 0) or 0 for test in tests)
        count = len(tests)
        average_score = total_score / count if count > 0 else 0
        average_grade = (average_score / 12) * 10

    return render_template('leaderboard_student.html',
                           student_name=student_name,
                           tests=tests,
                           average_score=average_score,
                           average_grade=average_grade)


# Logout - sesiunea utilizatorului se termină
@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('routes.login'))

# Login - autentificare profesor
@bp.route('/login', methods=['GET', 'POST'])
def login():
    # Dacă deja e autentificat, îl ducem direct în dashboard
    if current_user.is_authenticated:
        return redirect(url_for('routes.professor_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        users_collection = current_app.config.get('USERS_COLLECTION')
        user_dict = users_collection.find_one({'username': username})

        # Verificăm dacă parola este corectă
        if user_dict and check_password_hash(user_dict['password_hash'], password):
            user = User(user_dict)
            login_user(user)
            flash('Autentificare reușită!', 'success')
            return redirect(url_for('routes.professor_dashboard'))
        else:
            flash('Nume utilizator sau parolă incorecte!', 'danger')

    return render_template('login.html')

# Punctaj global pentru profesori
@bp.route('/leaderboard')
@login_required
@role_required('profesor')
def leaderboard():
    tests_collection = current_app.config.get("TESTS_COLLECTION")
    if tests_collection is None:
        return "Configurație colecție teste lipsă", 500

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

    color_map = {
        "grad 1": "green",
        "grad 2": "yellow",
        "grad 3": "red"
    }
    for entry in leaderboard_data:
        entry['color'] = color_map.get(entry['max_difficulty'], "black")

    return render_template('leaderboard.html', leaderboard=leaderboard_data)


# Generare PDF pentru punctajul global
@bp.route('/leaderboard/pdf')
@login_required
@role_required('profesor')
def leaderboard_pdf():
    tests_collection = current_app.config.get("TESTS_COLLECTION")
    if tests_collection is None:
        return "Configurație colecție teste lipsă", 500

    # Preluăm toate testele finalizate cu scor valid
    tests_cursor = tests_collection.find({
        "completed": True,
        "score": {"$ne": None}
    }).sort([("student_name", 1), ("completed_at", -1)])

    tests = list(tests_cursor)

    # Calculăm media punctajelor și medie echivalată pe student
    # Grupăm testele după student_name
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

    # Calculăm mediile
    for student in students.values():
        student["average_score"] = student["total_score"] / student["count"] if student["count"] > 0 else 0
        student["average_grade"] = (student["average_score"] / 12) * 10

    rendered = render_template(
        'leaderboard_pdf.html',
        students=students
    )

    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(rendered, dest=pdf)
    if pisa_status.err:
        return "Eroare la generarea PDF-ului", 500

    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=Punctaj_Global.pdf'
    return response


# Generare PDF pentru punctajul individual al studentului
@bp.route('/leaderboard/student/<student_name>/pdf')
def leaderboard_student_pdf(student_name):
    tests_collection = current_app.config.get("TESTS_COLLECTION")
    if tests_collection is None:
        return "Configurație colecție teste lipsă", 500

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

    rendered = render_template('leaderboard_student_pdf.html',
                               student_name=student_name,
                               tests=tests,
                               average_score=average_score,
                               average_grade=average_grade)
    
    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(rendered, dest=pdf)
    if pisa_status.err:
        return "Eroare la generarea PDF-ului", 500

    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Punctaj_{student_name}.pdf'
    return response