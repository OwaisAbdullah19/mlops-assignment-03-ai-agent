"""Print only a JWT; password is read without terminal echo."""

import getpass
import os

import httpx


def main():
    username = input("Airflow username [admin]: ").strip() or "admin"
    password = getpass.getpass("Airflow password: ")
    response = httpx.post(
        os.getenv("AIRFLOW_URL", "http://localhost:8080").rstrip("/") + "/auth/token",
        json={"username": username, "password": password},
        timeout=15,
    )
    if response.status_code != 201 and response.status_code != 200:
        raise SystemExit(f"Authentication failed (HTTP {response.status_code})")
    print(response.json()["access_token"])


if __name__ == "__main__":
    main()
