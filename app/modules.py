import subprocess
import os
from functools import partial
import pathlib as pl
import logging
import boto3
from botocore.exceptions import ClientError
from flask import url_for
from datetime import datetime


def upload_file(file_name, bucket, object_name):
    s3_client = boto3.client("s3")
    try:
        s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True


print = partial(print, flush=True)

# bytes pretty-printing
UNITS_MAPPING = [
    (1 << 50, " PB"),
    (1 << 40, " TB"),
    (1 << 30, " GB"),
    (1 << 20, " MB"),
    (1 << 10, " KB"),
    (1, (" byte", " bytes")),
]


def pretty_size(bytes, units=UNITS_MAPPING):
    """Get human-readable file sizes.
    simplified version of https://pypi.python.org/pypi/hurry.filesize/
    """
    for factor, suffix in units:
        if bytes >= factor:
            break
    amount = int(bytes / factor)

    if isinstance(suffix, tuple):
        singular, multiple = suffix
        if amount == 1:
            suffix = singular
        else:
            suffix = multiple
    return str(amount) + suffix


def mount_bkt():
    s3_bkt = os.getenv("AWS_S3_BUCKET")
    mnt_pt = f"/{s3_bkt}"
    if not os.path.exists(mnt_pt):
        try:
            os.mkdir(mnt_pt)
        except FileExistsError:
            print("fixing the mount point from mount_bkt()...")
            subprocess.call(["fusermount", "-u", mnt_pt, "&&", "fusermount", "-u", mnt_pt])
            subprocess.check_output(["goofys", s3_bkt, mnt_pt])
            return mnt_pt
    if len(list(pl.Path(mnt_pt).glob("*"))) == 0:
        print(f"mounting bucket {s3_bkt}")
        subprocess.check_output(["goofys", s3_bkt, mnt_pt])
    return mnt_pt


def validate_dir_name(dir_name):
    for char in r"""`~!@#$%^&*()=+[{]}\|:;"'<,>.?/ """:
        if char in dir_name:
            return False
    return True


def make_temp_dir(tmp_dir):
    if not os.path.exists(tmp_dir):
        os.mkdir(tmp_dir)
    return


def dir_contents(pth: pl.Path):
    try:
        dir_content = pth.glob("*")
    except OSError:
        print("fixing the mount mount from dir_contents()...")
        mount_bkt()
        dir_content = pth.glob("*")
    dir_list = []
    file_list = []
    for x in dir_content:
        stat = x.stat()
        if x.is_file():
            url = url_for("download_file", filepath=str(x))
            size = pretty_size(stat.st_size)
            mod = datetime.fromtimestamp(stat.st_mtime).strftime("%A, %B %d, %Y %I:%M:%S")
            item = {"link": url, "link_name": x.name, "size": size, "last_modified": mod, "is_dir": False}
            file_list.append(item)
        else:
            url = url_for("within_dir", dir_path=str(x))
            item = {"link": url, "link_name": x.name, "size": "--", "last_modified": "--", "is_dir": True}
            dir_list.append(item)

    return sorted(dir_list, key=lambda d: d["link_name"]) + sorted(file_list, key=lambda d: d["link_name"])
