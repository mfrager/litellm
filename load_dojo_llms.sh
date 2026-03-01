#!/bin/bash

python -m dojo.scripts.populate_models \
  --provider "lmstudio/,http://host.docker.internal:8000/v1,http://localhost:8000" \
  --provider "lmstudio_z/,http://bobs-mac.local:8000/v1,http://localhost:8000" \
  --write-config

