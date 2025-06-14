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

bp = Blueprint("routes", __name__)

# Decorator pentru roluri (ex: profesor)
def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator

# Ruta principală - redirecționează la login indiferent dacă ești autentificat
@bp.route('/')
def home():
    return redirect(url_for('routes.login'))

# Dashboard profesor - generare test
@bp.route('/professor_dashboard', methods=['GET', 'POST'])
@login_required
@role_required('profesor')
def professor_dashboard():
    test_url = None
    if request.method == 'POST':
        student_name = request.form.get('student_name')
        difficulty = request.form.get('difficulty')

        if not student_name or not difficulty:
            flash("Completează toate câmpurile!", "warning")
            return redirect(url_for('routes.professor_dashboard'))

        questions_collection = current_app.config.get("QUESTIONS_COLLECTION")
        tests_collection = current_app.config.get("TESTS_COLLECTION")

        domains = ["Cinematica", "Dinamica", "Statica"]
        selected_questions = []

        for domain in domains:
            qs = list(questions_collection.find({"domain": domain, "difficulty": difficulty}))
            if len(qs) < 4:
                flash(f"Nu sunt suficiente întrebări pentru domeniul {domain} la dificultatea {difficulty}.", "danger")
                return redirect(url_for('routes.professor_dashboard'))
            selected_questions += random.sample(qs, 4)

        random.shuffle(selected_questions)

        test_id = str(uuid4())
        test_doc = {
            "_id": test_id,
            "student_name": student_name,
            "difficulty": difficulty,
            "questions": selected_questions,
            "answers": {},
            "score": None,
            "completed": False,
            "created_at": datetime.utcnow(),
            "completed_at": None,
            "expires_at": datetime.utcnow() + timedelta(minutes=10)  # Expirare test 10 min
        }
        tests_collection.insert_one(test_doc)

        # Folosim ruta take_test care redirecționează la /quiz
        test_url = url_for('routes.take_test', test_id=test_id, _external=True)
        flash("Test creat cu succes!", "success")

    return render_template('professor_dashboard.html', test_url=test_url)

# Ruta de redirect pentru test, care duce la pagina quiz cu parametru test_id
@bp.route('/take_test/<test_id>')
@login_required
@role_required('profesor')
def take_test(test_id):
    return redirect(url_for('routes.quiz', test_id=test_id))

# Pagina de test pentru student
@bp.route('/quiz', methods=['GET', 'POST'])
def quiz():
    test_id = request.args.get('test_id')
    if not test_id:
        return "ID-ul testului lipsește.", 400

    tests_collection = current_app.config.get("TESTS_COLLECTION")
    test_doc = tests_collection.find_one({"_id": test_id})
    if not test_doc:
        return "Testul nu există.", 404

    time_left = (test_doc['expires_at'] - datetime.utcnow()).total_seconds()
    if time_left < 0:
        time_left = 0

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

    return render_template(
        'quiz.html',
        questions=test_doc['questions'],
        user_name=test_doc['student_name'],
        test_id=test_id,
        time_left=int(time_left)
    )

# Clasament individual student
@bp.route('/leaderboard/student/<student_name>')
def leaderboard_student(student_name):
    tests_collection = current_app.config.get("TESTS_COLLECTION")
    if tests_collection is None:
        return "Configurație colecție teste lipsă", 500

    # Selectăm testele finalizate ale studentului
    tests_cursor = tests_collection.find({
        "student_name": student_name,
        "completed": True,
        "score": {"$ne": None}
    }).sort("completed_at", -1)

    tests = list(tests_cursor)

    if not tests:
        average_score = 0
        average_grade = 0
    else:
        total_score = sum(test['score'] for test in tests if test.get('score') is not None)
        count = len(tests)
        average_score = total_score / count if count > 0 else 0
        average_grade = (average_score / 12) * 10

    return render_template('leaderboard_student.html',
                           student_name=student_name,
                           tests=tests,
                           average_score=average_score,
                           average_grade=average_grade)


# Logout
@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('routes.login'))

# Login
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('routes.professor_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        users_collection = current_app.config.get('USERS_COLLECTION')
        user_dict = users_collection.find_one({'username': username})

        if user_dict and check_password_hash(user_dict['password_hash'], password):
            user = User(user_dict)
            login_user(user)
            flash('Autentificare reușită!', 'success')
            return redirect(url_for('routes.professor_dashboard'))
        else:
            flash('Nume utilizator sau parolă incorecte!', 'danger')

    return render_template('login.html')

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
            "average_score": {"$avg": "$score"},
            "tests_count": {"$sum": 1}
        }},
        {"$sort": {"average_score": -1}}
    ]

    leaderboard_data = list(tests_collection.aggregate(pipeline))

    return render_template('leaderboard.html', leaderboard=leaderboard_data)

@bp.route('/leaderboard/pdf')
@login_required
@role_required('profesor')
def leaderboard_pdf():
    tests_collection = current_app.config.get("TESTS_COLLECTION")
    if tests_collection is None:
        return "Error: TESTS_COLLECTION not found in config", 500

    pipeline = [
        {"$match": {"completed": True, "score": {"$ne": None}}},
        {"$group": {
            "_id": "$student_name",
            "average_score": {"$avg": "$score"},
            "tests_count": {"$sum": 1}
        }},
        {"$sort": {"average_score": -1}}
    ]

    leaderboard_data = list(tests_collection.aggregate(pipeline))

    rendered = render_template("leaderboard_pdf.html", leaderboard=leaderboard_data)

    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(rendered, dest=pdf)
    if pisa_status.err:
        return "Eroare la generarea PDF-ului", 500

    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=Punctaj_Global.pdf'
    return response

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
    response.headers['Content-Disposition'] = f'attachment; filename=Clasament_{student_name}.pdf'
    return response


