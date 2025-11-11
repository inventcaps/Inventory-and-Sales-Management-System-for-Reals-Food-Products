#!/usr/bin/env bash
# exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python projectsite/manage.py collectstatic --no-input
python projectsite/manage.py migrate
