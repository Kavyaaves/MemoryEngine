"""Shared test setup: tests never touch the developer's cloud services, whatever backend/.env says."""

import os

# Real environment variables win over backend/.env, so these override it for every test.
os.environ["STORAGE_BACKEND"] = "local"
