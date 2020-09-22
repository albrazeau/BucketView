from flask import Flask, redirect, url_for, send_file, request, flash, render_template
from werkzeug.utils import secure_filename
from wtforms import Form, FileField, validators
import pathlib as pl
import os
from modules import mount_bkt


MOUNT_POINT = mount_bkt()
AWS_BUCKET = os.getenv("AWS_S3_BUCKET")
app = Flask(__name__)
app.config["SECRET_KEY"] = "a super secret key"


class ReusableForm(Form):
    input_file = FileField("input_file:", validators=[validators.DataRequired()])


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

    os.chdir(MOUNT_POINT)
    cwd = pl.Path(os.getcwd())

    if request.method == "GET":
        html_content_list = dir_contents(cwd)
        bucket_content = "<center>" + html_content_list + "</center>"
        return render_template("main.html", form=form, bucket_content=bucket_content, aws_bucket=AWS_BUCKET)

    else:
        input_file = request.files["input_file"]
        filename = secure_filename(input_file.filename)
        inputfile = os.path.join(str(cwd), filename)
        input_file.save(inputfile)
        flash(f"Successfully uploaded {filename}")
        return redirect(request.url)


@app.route(f"/explorer/<path:dir_path>", methods=["GET", "POST"])
def within_dir(dir_path):

    form = ReusableForm(request.form)
    print(form.errors)

    os.chdir("/" + dir_path)
    cwd = pl.Path(os.getcwd())

    if request.method == "GET":
        html_content_list = dir_contents(cwd)
        bucket_content = "<center>" + html_content_list + "</center>"
        return render_template("main.html", form=form, bucket_content=bucket_content, aws_bucket=AWS_BUCKET)

    else:
        input_file = request.files["input_file"]
        filename = secure_filename(input_file.filename)
        inputfile = os.path.join(str(cwd), filename)
        input_file.save(inputfile)
        flash(f"Successfully uploaded {filename}")
        return redirect(request.url)


@app.route(f"/download/<path:filepath>")
def download_file(filepath):
    return send_file("/" + filepath, as_attachment=True)
