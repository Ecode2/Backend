#!/bin/bash
#Exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Apply database migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput #--upload-unhashed-files
python manage.py deleteorphanedmedia
python manage.py deleteredundantstatic #--keep-unhashed-files


echo "Build completed successfully."
