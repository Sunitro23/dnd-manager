#!/usr/bin/env sh
set -eu

.venv/bin/ruff check .
.venv/bin/python scripts/check_architecture.py
npm run lint:css
.venv/bin/pysassc --style compressed static/styles.scss /tmp/dnd-manager-styles.css
cmp static/styles.css /tmp/dnd-manager-styles.css
.venv/bin/python -m unittest discover -v
node --check static/app.js
node --check static/character-create.js
node --check static/character-admin.js
