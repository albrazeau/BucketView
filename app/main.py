from flask import (
    Flask,
    redirect,
    url_for,
    send_file,
    request,
    flash,
    render_template,
    after_this_request,
    send_from_directory,
    jsonify,
    make_response,
    Response,
)
from flask_login import LoginManager, login_required, current_user, logout_user, login_user
from werkzeug.utils import secure_filename
from wtforms import Form, FileField, TextField, StringField, PasswordField, BooleanField, SubmitField, TextAreaField
from wtforms.validators import DataRequired
from flask_wtf import FlaskForm
import pathlib as pl
import os
import json
import requests
from shutil import make_archive
import logging
from datetime import datetime
from functools import wraps
from github import Github
from modules import mount_bkt, validate_dir_name, make_temp_dir, upload_file, dir_contents, pretty_size
from functools import partial
from db import db_init_app, User


MOUNT_POINT = mount_bkt()
AWS_BUCKET = os.getenv("AWS_S3_BUCKET")
FLASK_LOG = "/var/log/nginx/flask.log"

app = Flask(__name__)

logging.basicConfig(filename=FLASK_LOG, level=logging.WARN)

app.config["SECRET_KEY"] = "a super secret key"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.getenv('SQLITE_DB')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TEMP_DIR"] = "/temp-flask-dir"
make_temp_dir(app.config["TEMP_DIR"])

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

db = db_init_app(app)

print = partial(print, flush=True)


def nocache(view):
    @wraps(view)
    def no_cache_view(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, private, max-age=0")
        return response

    return no_cache_view


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"), "favicon.ico", mimetype="image/vnd.microsoft.icon"
    )


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


class ReusableForm(Form):
    input_file = FileField("input_file:")
    create_dir = TextField("create_dir:")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Sign In")


class IssueForm(FlaskForm):
    bug_title = StringField("Title", validators=[DataRequired()])
    bug_report = TextAreaField("Bug Report", validators=[DataRequired()], render_kw={"class": "bug-report-body"})
    urgent = BooleanField("This is urgent")
    submit = SubmitField("Submit")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid username or password", "error")
            app.logger.warn(f" {str(datetime.now())}: {form.email.data} login failed")
            return redirect(url_for("login"))
        login_user(user, remember=form.remember_me.data)
        app.logger.warn(f" {str(datetime.now())}: {user.email} successfully logged in")
        return redirect(url_for("index"))
    return render_template("login.html", title="Sign In", form=form)


@app.route("/report_bug", methods=["GET", "POST"])
@login_required
def report_bug():
    email = current_user.email
    form = IssueForm()

    if form.validate_on_submit():

        body = form.bug_report.data + f"\n\n*Submitted by: {email}*"
        body = body + "\n\n**This issue is urgent**" if form.urgent.data else body

        client = Github(os.getenv("GIT_TOKEN"))
        repo = client.get_repo(f"{os.getenv('GIT_ORG')}/{os.getenv('GIT_REPO')}")
        issue = repo.create_issue(
            title=form.bug_title.data,
            body=body + "\n\n*This issue was created through BucketView*",
            assignees=list(repo.get_contributors()),
        )

        app.logger.warn(f" {str(datetime.now())}: {email} successfully submitted a bug report - {issue}")

        flash("Bug report submitted successfully", "success")

        return render_template("issue.html", title="Report Bug", form=form)

    return render_template("issue.html", title="Report Bug", form=form)


@app.route("/")
@login_required
def index():
    return redirect(f"/explorer/{AWS_BUCKET}")


@nocache
@app.route(f"/explorer/{AWS_BUCKET}", methods=["GET", "POST"])
@login_required
def explorer():

    form = ReusableForm(request.form)
    # print(form.errors)

    dir_path = pl.Path(MOUNT_POINT)

    if request.method == "GET":
        html_content_list = dir_contents(dir_path)
        nav_parts = [x for x in dir_path.parts if x != "/"]
        return render_template(
            "main.html",
            form=form,
            bucket_content=html_content_list,
            aws_bucket=AWS_BUCKET,
            nav_parts=nav_parts,
            nav_len=len(nav_parts),
        )

    else:
        create_dir = request.form["create_dir"]
        if create_dir and validate_dir_name(create_dir):
            new_dir = os.path.join(str(dir_path), create_dir)
            if not os.path.exists(new_dir):
                os.mkdir(new_dir)
                flash(f"Successfully created {create_dir}!", "success")
                app.logger.warn(
                    f" {str(datetime.now())}: {current_user.email} successfully created a directory: {create_dir}"
                )
                return redirect(request.url)
            else:
                flash(f"{create_dir} already exists!", "error")
                app.logger.warn(
                    f" {str(datetime.now())}: {current_user.email} failed to create directory: {create_dir} - it already exists"
                )
                return redirect(request.url)
        elif create_dir and not validate_dir_name(create_dir):
            illegal_chars = r"""`~!@#$%^&*()=+[{]}\|:;"'<,>.?/"""
            flash(
                f"Error creating {create_dir}, cannot contain a space or the following characters: {illegal_chars}",
                "error",
            )
            app.logger.warn(
                f" {str(datetime.now())}: {current_user.email} failed to create directory: {create_dir} - it contains a special character"
            )
            return redirect(request.url)

        input_file = request.files["input_file"]
        filename = secure_filename(input_file.filename)
        if filename:
            tmpfile = os.path.join(app.config["TEMP_DIR"], filename)
            input_file.save(tmpfile)
            uploaded_target_file = os.path.join(str(dir_path), filename)
            if upload_file(tmpfile, AWS_BUCKET, uploaded_target_file.split(MOUNT_POINT + "/")[1]):
                flash(f"Successfully uploaded {filename}", "success")
                app.logger.warn(
                    f" {str(datetime.now())}: {current_user.email} successfully uploaded a {pretty_size(os.stat(tmpfile).st_size)} file: {uploaded_target_file}"
                )
            else:
                flash(f"Error uploading {filename}", "error")
                app.logger.error(
                    f" {str(datetime.now())}: {current_user.email} error uploading a {pretty_size(os.stat(tmpfile).st_size)} file to s3: {uploaded_target_file}"
                )
            os.remove(tmpfile)
            return redirect(request.url)
        return redirect(request.url)


@nocache
@app.route(f"/explorer/<path:dir_path>", methods=["GET", "POST"])
@login_required
def within_dir(dir_path):

    form = ReusableForm(request.form)
    # print(form.errors)

    dir_path = pl.Path("/" + dir_path)

    if request.method == "GET":
        html_content_list = dir_contents(dir_path)
        nav_parts = [x for x in dir_path.parts if x != "/"]
        return render_template(
            "main.html",
            form=form,
            bucket_content=html_content_list,
            aws_bucket=AWS_BUCKET,
            nav_parts=nav_parts,
            nav_len=len(nav_parts),
        )

    else:
        create_dir = request.form["create_dir"]
        if create_dir and validate_dir_name(create_dir):
            new_dir = os.path.join(str(dir_path), create_dir)
            if not os.path.exists(new_dir):
                os.mkdir(new_dir)
                flash(f"Successfully created {create_dir}!", "success")
                app.logger.warn(
                    f" {str(datetime.now())}: {current_user.email} successfully created a directory: {create_dir}"
                )
                return redirect(request.url)
            else:
                flash(f"{create_dir} already exists!", "error")
                app.logger.warn(
                    f" {str(datetime.now())}: {current_user.email} failed to create directory: {create_dir} - it already exists"
                )
                return redirect(request.url)
        elif create_dir and not validate_dir_name(create_dir):
            illegal_chars = r"""`~!@#$%^&*()=+[{]}\|:;"'<,>.?/"""
            flash(
                f"Error creating {create_dir}, cannot contain a space or the following characters: {illegal_chars}",
                "error",
            )
            app.logger.warn(
                f" {str(datetime.now())}: {current_user.email} failed to create directory: {create_dir} - it contains a special character"
            )
            return redirect(request.url)

        input_file = request.files["input_file"]
        filename = secure_filename(input_file.filename)
        if filename:
            tmpfile = os.path.join(app.config["TEMP_DIR"], filename)
            input_file.save(tmpfile)
            uploaded_target_file = os.path.join(str(dir_path), filename)
            if upload_file(tmpfile, AWS_BUCKET, uploaded_target_file.split(MOUNT_POINT + "/")[1]):
                flash(f"Successfully uploaded {filename}", "success")
                app.logger.warn(
                    f" {str(datetime.now())}: {current_user.email} successfully uploaded a {pretty_size(os.stat(tmpfile).st_size)} file: {uploaded_target_file}"
                )
            else:
                flash(f"Error uploading {filename}", "error")
                app.logger.error(
                    f" {str(datetime.now())}: {current_user.email} error uploading a {pretty_size(os.stat(tmpfile).st_size)} file to s3: {uploaded_target_file}"
                )
            os.remove(tmpfile)
            return redirect(request.url)
        return redirect(request.url)


@app.route(f"/download/<path:filepath>")
@login_required
def download_file(filepath):
    app.logger.warn(f" {str(datetime.now())}: {current_user.email} downloaded file: {filepath}")
    return send_file("/" + filepath, as_attachment=True, cache_timeout=1)


@app.route(f"/download/dir/<path:dir_path>")
@login_required
def download_dir(dir_path):

    dir_path = pl.Path("/" + dir_path)

    output_zipfile = os.path.join(app.config["TEMP_DIR"], dir_path.stem)

    make_archive(output_zipfile, "zip", dir_path)

    @after_this_request
    def remove_file(response):
        os.remove(output_zipfile + ".zip")
        return response

    app.logger.warn(f" {str(datetime.now())}: {current_user.email} downloaded directory: {str(dir_path) + '.zip'}")
    return send_file(output_zipfile + ".zip", as_attachment=True)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/background_reprocess/<path:filepath>")
@login_required
def background_reprocess(filepath):
    filepath = filepath if filepath.startswith("/") else "/" + filepath
    print(f"Reprocessing: {filepath}")
    r = requests.post("http://api:5678/reprocess_geopackage", json={"gpkg_path": filepath})
    try:
        r.raise_for_status()
    except:
        print("Background request failed:")
        print(r.text)
        return r.text, r.status_code
    print(r.json())
    return ""


@app.route("/background_compute_leveed_area/<path:filepath>")
@login_required
def background_compute_leveed_area(filepath):
    filepath = filepath if filepath.startswith("/") else "/" + filepath
    print(f"Computing Leveed Area: {filepath}")
    r = requests.post("http://api:5678/compute_leveed_areas", json={"gpkg_path": filepath})
    try:
        r.raise_for_status()
    except:
        print("Background request failed:")
        print(r.text)
        return r.text, r.status_code
    print(r.json())
    return ""


@app.route("/background_create_report/<path:filepath>")
@login_required
def background_create_report(filepath):
    filepath = filepath if filepath.startswith("/") else "/" + filepath
    print(f"Computing Leveed Area: {filepath}")
    r = requests.post("http://api:5678/create_report", json={"gpkg_path": filepath})
    try:
        r.raise_for_status()
    except:
        print("Background request failed:")
        print(r.text)
        return r.text, r.status_code
    print(r.json())
    return ""


@nocache
@app.route("/view/<path:filepath>")
@login_required
def view_file(filepath):
    try:
        filepath = filepath if filepath.startswith("/") else "/" + filepath

        if filepath.endswith(".json"):
            with open(filepath, "r") as f:
                return jsonify(json.load(f))

        elif filepath.endswith(".html") or filepath.endswith(".csv") or filepath.endswith(".log"):
            with open(filepath, "r") as f:
                return f.read()

        elif filepath.endswith(".png"):
            with open(filepath, "rb") as f:
                return Response(response=f.read(), status=200, mimetype="image/png")

        else:
            return jsonify(f"Unable to view this file type: {os.path.splitext(filepath)[1]}"), 400
    except Exception as e:
        app.logger.error(f" {str(datetime.now())}: error viewing file {filepath}: {str(e)}")
        return f"<br><br><center><h1>Error viewing file: {str(e)}</h1></center>", 500