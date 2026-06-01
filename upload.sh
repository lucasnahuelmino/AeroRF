#!/usr/bin/env bash
# Helper script to add remote and push to GitHub.
# Usage: ./upload.sh <remote-url>

if [ -z "$1" ]; then
  echo "Usage: $0 <git-remote-url>"
  exit 1
fi

git remote add origin "$1"
git branch -M main
git push -u origin main

echo "Pushed to $1"
