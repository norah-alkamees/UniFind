import io
import pytest
from app import create_app, db


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "MAX_CONTENT_LENGTH": 5 * 1024 * 1024,
    })
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in(client):
    client.post("/register", data={"email": "student@pnu.edu.sa", "password": "strongpass123"})
    return client


def png_upload():
    # Tiny valid PNG signature is sufficient for this extension-validation implementation.
    return (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 24), "campus.png")
