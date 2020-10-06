from flask import Flask, redirect, url_for, send_file, request, flash, render_template
from werkzeug.utils import secure_filename
from wtforms import Form, FileField, validators, TextField
import pathlib as pl
import os
from modules import mount_bkt, validate_dir_name
from functools import partial


MOUNT_POINT = mount_bkt()
AWS_BUCKET = os.getenv("AWS_S3_BUCKET")
app = Flask(__name__)
app.config["SECRET_KEY"] = "a super secret key"

print = partial(print, flush=True)


class ReusableForm(Form):
    input_file = FileField("input_file:")  # , validators=[validators.DataRequired()])
    create_dir = TextField("create_dir:")


def dir_contents(pth: pl.Path):
    dir_content = list(pth.glob("*"))
    html_content_list = []
    for x in dir_content:
        if x.is_file():
            download_url = url_for("download_file", filepath=str(x))
            item = f'<br><a href="{download_url}">{x.name}</a><br>'
            html_content_list.append(item)
        else:
            redirect_url = url_for("within_dir", dir_path=str(x))
            item = f'<br><a href="{redirect_url}">{x.name}/</a><br>'
            html_content_list.append(item)
    return "".join(html_content_list)


@app.route("/")
def index():
    return redirect(f"/explorer/{AWS_BUCKET}")


@app.route(f"/explorer/{AWS_BUCKET}", methods=["GET", "POST"])
def explorer():

    form = ReusableForm(request.form)
    print(form.errors)

    dir_path = pl.Path("/" + MOUNT_POINT)

    if request.method == "GET":
        html_content_list = dir_contents(dir_path)
        bucket_content = "<center>" + html_content_list + "</center>"
        return render_template("main.html", form=form, bucket_content=bucket_content, aws_bucket=AWS_BUCKET)

    else:
        create_dir = request.form["create_dir"]
        if create_dir and validate_dir_name(create_dir):
            new_dir = os.path.join(str(dir_path), create_dir)
            os.mkdir(new_dir)
            flash(f"Successfully created {create_dir}")
            return redirect(request.url)

        input_file = request.files["input_file"]
        filename = secure_filename(input_file.filename)
        inputfile = os.path.join(str(dir_path), filename)
        input_file.save(inputfile)
        flash(f"Successfully uploaded {filename}")
        return redirect(request.url)


@app.route(f"/explorer/<path:dir_path>", methods=["GET", "POST"])
def within_dir(dir_path):

    form = ReusableForm(request.form)
    print(form.errors)

    dir_path = pl.Path("/" + dir_path)

    if request.method == "GET":
        html_content_list = dir_contents(dir_path)
        bucket_content = "<center>" + html_content_list + "</center>"
        return render_template("main.html", form=form, bucket_content=bucket_content, aws_bucket=AWS_BUCKET)

    else:
        create_dir = request.form["create_dir"]
        if create_dir and validate_dir_name(create_dir):
            new_dir = os.path.join(str(dir_path), create_dir)
            os.mkdir(new_dir)
            flash(f"Successfully created {create_dir}")
            return redirect(request.url)

        input_file = request.files["input_file"]
        filename = secure_filename(input_file.filename)
        inputfile = os.path.join(str(dir_path), filename)
        input_file.save(inputfile)
        flash(f"Successfully uploaded {filename}")
        return redirect(request.url)


@app.route(f"/download/<path:filepath>")
def download_file(filepath):
    return send_file("/" + filepath, as_attachment=True)
