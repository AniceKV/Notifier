#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files and apply database migrations
python djangoproj/manage.py collectstatic --no-input
python djangoproj/manage.py migrate
