import subprocess
import os
from functools import partial
import pathlib as pl
import logging
import boto3
from botocore.exceptions import ClientError


def upload_file(file_name, bucket, object_name):
    s3_client = boto3.client("s3")
    try:
        s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True


print = partial(print, flush=True)


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