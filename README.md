# UniFind

UniFind is a university lost and found application built with Flask, SQLite, SQLAlchemy, Flask-Login, and Werkzeug password hashing. Students register using a `@pnu.edu.sa` address, post lost or found listings, upload an optional photo, and browse listings by category and campus location.

## Requirements

- Python 3.10 or newer
- pip

## Run locally (Windows PowerShell)

1. Open PowerShell in this project folder.
2. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process Bypass` in that terminal, then activate again.
3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```
4. Set a private development secret (use a different random value for a real deployment):

   ```powershell
   $env:UNIFIND_SECRET_KEY = [guid]::NewGuid().ToString() + [guid]::NewGuid().ToString()
   ```
5. Start the application:

   ```powershell
   python app.py
   ```
6. Open http://127.0.0.1:5000 in your browser. The SQLite database and uploaded photos are created under the `instance` folder on first run.

## Run tests

```powershell
python -m pytest -q
```

## Configuration

- `UNIFIND_SECRET_KEY`: Flask session signing secret. Set this in the environment; never commit it.
- `DATABASE_URL`: SQLAlchemy database URL. Defaults to SQLite at `instance/unifind.db`.
- `UPLOAD_FOLDER`: photo directory. Defaults to `instance/uploads`.
- Campus locations and categories are defined near the top of `app.py` and can be edited to match the campus.

## Included features

- University email registration, login sessions, logout, and protected listing creation.
- Lost and found item listings with category, description, campus location, date, and optional image.
- Image extension allowlist and 5 MB request limit.
- Combined category, location, and listing-type filters.
- Responsive English interface.

The database tables are `users` and `items`; each item belongs to a user through a foreign key and ORM relationship.
