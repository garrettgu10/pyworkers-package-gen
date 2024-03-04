import os
import json
from pathlib import Path
import tempfile
import zipfile
import tarfile
import uuid
import boto3
import re

def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()

# See setup.sh
# prerequisite: emsdk, pyodide, packages -> pyodide/packages

# creates a package bundle .tar.zip file to be bundled in with edgeworker
# the resulting bundle is written to dist/pyodide_packages.tar.zip
def make_bundle(dist = Path("dist")):
    with open(dist / "pyodide-lock.json", "r") as file:
        lock = json.load(file)
    with tempfile.TemporaryDirectory(delete=False) as t:
        tempdir = Path(t)
        print("making bundle in " + str(tempdir))
        # copy pyodide-lock.json into tempdir
        with open(tempdir / "pyodide-lock.json", "w") as file:
            json.dump(lock, file)
        for package in lock["packages"].values():
            name = normalize(package["name"])
            if name.endswith("-tests") or name == "test": 
                os.mkdir(tempdir / name)
                continue
            file = dist / package["file_name"]
            with zipfile.ZipFile(file, "r") as zip:
                zip.extractall(tempdir / name)
        # create temp tarfile from tempdir
        with tarfile.open(tempdir / "pyodide_packages.tar", "w") as tar:
            tar.add(tempdir, arcname="./")
        # create zip file in dist/ from tarfile
        with zipfile.ZipFile(dist / "pyodide_packages.tar.zip", "w", compression=zipfile.ZIP_DEFLATED) as zip:
            zip.write(tempdir / "pyodide_packages.tar", "pyodide_packages.tar")

# uploads everything in dist to python-package-bucket at tag/...
def upload_to_r2(dist = Path("dist"), tag = str(uuid.uuid4())):
    # upload to r2
    s3 = boto3.client("s3", 
                      endpoint_url = "https://" + os.environ.get("R2_ACCOUNT_ID") + ".r2.cloudflarestorage.com",
                      aws_access_key_id = os.environ.get("R2_ACCESS_KEY_ID"),
                      aws_secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY"),
                      region_name="auto")
    
    # upload entire dist directory to r2
    for root, dirs, files in os.walk(dist):
        for file in files:
            path = Path(root) / file
            key = tag + "/" + str(path.relative_to(dist))
            print(f"uploading {path} to {key}")
            s3.upload_file(str(path), "python-package-bucket", key)

if __name__ == "__main__":
    with open("required_packages.txt", "r") as file:
        required_packages = file.read().split("\n")
    status = os.system(f"pyodide build-recipes --install {' '.join(required_packages)}")
    if status != 0:
        raise Exception("Failed to build recipes")
    
    make_bundle()
    upload_to_r2()