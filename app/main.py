from flask import Flask, redirect, url_for, send_file, request, flash, render_template, after_this_request
from flask_login import LoginManager, login_required, current_user, logout_user, login_user
from werkzeug.utils import secure_filename
from wtforms import Form, FileField, validators, TextField, StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired
from flask_wtf import FlaskForm
import pathlib as pl
import os
import subprocess
from shutil import make_archive
import logging
from datetime import datetime
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


@app.route("/")
@login_required
def index():
    return redirect(f"/explorer/{AWS_BUCKET}")


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
                app.logger.warn(f" {str(datetime.now())}: {current_user.email} successfully created a directory: {create_dir}")
                return redirect(request.url)
            else:
                flash(f"{create_dir} already exists!", "error")
                app.logger.warn(f" {str(datetime.now())}: {current_user.email} failed to create directory: {create_dir} - it already exists")
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
                app.logger.warn(f" {str(datetime.now())}: {current_user.email} successfully created a directory: {create_dir}")
                return redirect(request.url)
            else:
                flash(f"{create_dir} already exists!", "error")
                app.logger.warn(f" {str(datetime.now())}: {current_user.email} failed to create directory: {create_dir} - it already exists")
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
    return send_file("/" + filepath, as_attachment=True)


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
