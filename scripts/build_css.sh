#!/usr/bin/env sh
set -eu

.venv/bin/pysassc --style compressed static/styles.scss static/styles.css
