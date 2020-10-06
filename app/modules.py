import subprocess
import os


def mount_bkt():
    s3_bkt = os.getenv("AWS_S3_BUCKET")
    mnt_pt = f"/{s3_bkt}"
    if not os.path.exists(mnt_pt):
        os.mkdir(mnt_pt)
    subprocess.check_output(["goofys", s3_bkt, mnt_pt])
    return mnt_pt


def validate_dir_name(dir_name):
    for char in r"""`~!@#$%^&*()=+[{]}\|:;"'<,>.?/ """:
        if char in dir_name:
            return False
    return True
