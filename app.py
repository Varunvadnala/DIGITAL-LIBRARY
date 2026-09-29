import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data.json"
EDUCATION_LEVELS = ["School", "Higher Secondary", "Undergraduate", "Postgraduate", "Working", "Other"]
SURVEY_OPTIONS = {
    "age_group": ["Below 15", "15–18", "19–25", "26–40", "Above 40"],
    "education": EDUCATION_LEVELS,
    "resource_use": ["Books", "PDFs", "Videos", "Audio Books", "Websites", "Notes"],
    "problems": ["Limited books", "Expensive books", "Difficulty finding relevant material", "Lack of digital resources", "Poor internet access", "Lack of guidance", "Other"],
    "device": ["Smartphone", "Laptop", "Desktop", "Tablet", "Other"],
    "interest": ["Definitely", "Probably", "Not Sure", "Probably Not", "No"],
    "feature": ["Search", "Category-wise browsing", "E-Books", "Audio Books", "Downloadable material", "Recommendations", "Favorites", "Other"],
}
EMPTY_STORE = {"books": [], "audio_books": [], "users": [], "surveys": []}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def load_data():
    if not DATA_FILE.exists():
        save_data(EMPTY_STORE.copy())
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise RuntimeError("The library data file contains invalid JSON.") from error
    if not isinstance(data, dict) or any(not isinstance(data.get(key), list) for key in EMPTY_STORE):
        raise RuntimeError("The library data file has an invalid structure.")
    return data


def save_data(data):
    handle, temporary_path = tempfile.mkstemp(dir=ROOT, prefix=".data.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_path, DATA_FILE)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def clean_text(value, limit=500):
    return (value or "").strip()[:limit]


def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    user = next((item for item in load_data()["users"] if item["id"] == user_id), None)
    if not user or user.get("disabled"):
        session.clear()
        return None
    return user


def next_id(items):
    return max((int(item.get("id", 0)) for item in items), default=0) + 1


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.context_processor
def template_values():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(24)
    return {"current_user": current_user(), "csrf_token": session["csrf_token"]}


@app.before_request
def check_post_token():
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(submitted, expected):
            abort(400)


@app.route("/")
def home():
    data = load_data()
    user = current_user()
    if not user:
        mode = "register" if not data["users"] else "login"
        return render_template("index.html", page="account", mode=mode, education_levels=EDUCATION_LEVELS)
    return render_template("index.html", page="home", data=data, survey_options=SURVEY_OPTIONS)


@app.route("/account", methods=["GET", "POST"])
def account():
    data = load_data()
    mode = request.args.get("mode", "register" if not data["users"] else "login")
    if mode not in ("register", "login"):
        abort(404)

    if request.method == "POST" and mode == "register":
        name = clean_text(request.form.get("name"), 100)
        study_field = clean_text(request.form.get("study_field"), 120)
        education_level = clean_text(request.form.get("education_level"), 50)
        institution = clean_text(request.form.get("institution"), 150)
        email = clean_text(request.form.get("email"), 254).casefold()
        password = request.form.get("password", "")
        valid_email = re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
        if not name or not study_field or education_level not in EDUCATION_LEVELS or not valid_email or len(password) < 8:
            flash("Complete your name, study area, academic level, valid email, and a password of at least 8 characters.", "error")
        elif password != request.form.get("confirm_password"):
            flash("The passwords do not match.", "error")
        elif any(user["email"] == email for user in data["users"]):
            flash("An account with that email already exists.", "error")
        else:
            data["users"].append({
                "id": next_id(data["users"]), "name": name, "study_field": study_field,
                "education_level": education_level, "institution": institution,
                "email": email, "password_hash": generate_password_hash(password),
                "created_at": now_iso(),
            })
            save_data(data)
            flash("Account created. Log in to continue.", "success")
            return redirect(url_for("account", mode="login"))

    if request.method == "POST" and mode == "login":
        email = clean_text(request.form.get("email"), 254).casefold()
        password = request.form.get("password", "")
        user = next((item for item in data["users"] if item["email"] == email and not item.get("disabled")), None)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(24)
            return redirect(url_for("home"))
        flash("Email or password was not recognized.", "error")

    return render_template("index.html", page="account", mode=mode, education_levels=EDUCATION_LEVELS)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/library")
def library():
    data = load_data()
    query = clean_text(request.args.get("q"), 100).casefold()
    category = clean_text(request.args.get("category"), 60)
    kind = clean_text(request.args.get("type"), 30)
    resources = [{**item, "kind": "E-Book"} for item in data["books"]]
    resources += [{**item, "kind": "Audio Book"} for item in data["audio_books"]]
    if query:
        resources = [item for item in resources if query in " ".join(str(item.get(key, "")) for key in ("title", "author", "category", "description", "source")).casefold()]
    if category:
        resources = [item for item in resources if item["category"] == category]
    if kind:
        resources = [item for item in resources if item["kind"] == kind]
    categories = sorted({item["category"] for item in data["books"] + data["audio_books"]})
    return render_template("index.html", page="library", resources=resources, categories=categories, filters={"q": request.args.get("q", ""), "category": category, "type": kind})


@app.route("/survey", methods=["GET", "POST"])
def survey():
    if request.method == "POST":
        answers = {}
        for key, allowed in SURVEY_OPTIONS.items():
            selected = request.form.getlist(key) if key == "problems" else [request.form.get(key, "")]
            if (key != "problems" and not selected[0]) or any(value not in allowed for value in selected):
                flash("Please answer each survey question using the listed options.", "error")
                return render_template("index.html", page="survey", survey_options=SURVEY_OPTIONS), 400
            answers[key] = selected if key == "problems" else selected[0]
        feedback = clean_text(request.form.get("feedback"), 2000)
        if not feedback:
            flash("Please enter your feedback.", "error")
            return render_template("index.html", page="survey", survey_options=SURVEY_OPTIONS), 400
        data = load_data()
        data["surveys"].append({"id": next_id(data["surveys"]), "submitted_at": now_iso(), **answers, "feedback": feedback})
        save_data(data)
        flash("Thank you. Your response has been saved.", "success")
        return redirect(url_for("home") if current_user() else url_for("survey"))
    return render_template("index.html", page="survey", survey_options=SURVEY_OPTIONS)


@app.route("/comparison")
def comparison():
    return render_template("index.html", page="comparison")


@app.errorhandler(400)
def bad_request(_error):
    return render_template("index.html", page="error", code=400, message="Please reload the page and try again."), 400


@app.errorhandler(404)
def not_found(_error):
    return render_template("index.html", page="error", code=404, message="That page could not be found."), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template("index.html", page="error", code=500, message="Something went wrong. Please try again."), 500


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
