from app import Item, ListingReport, User, db
from conftest import png_upload


def test_register_valid_university_email(client, app):
    response = client.post("/register", data={"email": "person@pnu.edu.sa", "password": "password123"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Your UniFind account is ready" in response.data
    with app.app_context():
        user = User.query.filter_by(email="person@pnu.edu.sa").one()
        assert user.password_hash != "password123"
        assert user.check_password("password123")


def test_reject_non_university_email(client):
    response = client.post("/register", data={"email": "person@gmail.com", "password": "password123"})
    assert b"ending in @pnu.edu.sa" in response.data


def test_login_and_logout(client):
    client.post("/register", data={"email": "person@pnu.edu.sa", "password": "password123"})
    client.post("/logout")
    response = client.post("/login", data={"email": "person@pnu.edu.sa", "password": "password123"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Browse listings" in response.data
    response = client.post("/logout", follow_redirects=True)
    assert b"You have been logged out" in response.data


def test_invalid_login(client):
    response = client.post("/login", data={"email": "nobody@pnu.edu.sa", "password": "wrongpass"})
    assert b"Email or password is incorrect" in response.data


def post_item(client, listing_type="lost", **extra):
    data = {"item_name": "Blue bottle", "category": "Electronics", "description": "Blue bottle near the library", "location": "Library", "date": "2026-10-01"}
    data.update(extra)
    return client.post(f"/items/new/{listing_type}", data=data, follow_redirects=True)


def test_lost_and_found_creation_persisted(client, app):
    client.post("/register", data={"email": "student@pnu.edu.sa", "password": "strongpass123"})
    assert post_item(client).status_code == 200
    assert post_item(client, "found", item_name="Found keys").status_code == 200
    with app.app_context():
        assert Item.query.count() == 2
        assert {i.listing_type for i in Item.query.all()} == {"LOST", "FOUND"}
        assert Item.query.filter_by(item_name="Blue bottle").one().location == "Library"


def test_lost_photo_upload(client, app):
    client.post("/register", data={"email": "student@pnu.edu.sa", "password": "strongpass123"})
    payload = {"item_name": "Lost phone", "category": "Electronics", "description": "Black phone", "location": "Library", "date": "2026-10-01", "photo": png_upload()}
    response = client.post("/items/new/lost", data=payload, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        item = Item.query.one()
        assert item.image_filename
        assert b"<img" in client.get("/listings").data


def test_found_photo_upload(client, app):
    client.post("/register", data={"email": "student@pnu.edu.sa", "password": "strongpass123"})
    payload = {"item_name": "Found notebook", "category": "Books & Notes", "description": "Green cover", "location": "Student Center", "date": "2026-10-01", "photo": png_upload()}
    client.post("/items/new/found", data=payload, content_type="multipart/form-data")
    with app.app_context():
        assert Item.query.one().image_filename


def test_invalid_image_upload_rejected(client, app):
    client.post("/register", data={"email": "student@pnu.edu.sa", "password": "strongpass123"})
    payload = {"item_name": "Bad upload", "category": "Electronics", "description": "Details", "location": "Library", "date": "2026-10-01", "photo": (bytes_file(), "malware.exe")}
    response = client.post("/items/new/lost", data=payload, content_type="multipart/form-data")
    assert b"Photo must be PNG" in response.data
    with app.app_context():
        assert Item.query.count() == 0


def test_oversized_photo_upload_rejected(client, app):
    import io
    client.post("/register", data={"email": "student@pnu.edu.sa", "password": "strongpass123"})
    payload = {"item_name": "Large upload", "category": "Electronics", "description": "Details", "location": "Library", "date": "2026-10-01", "photo": (io.BytesIO(b"x" * (5 * 1024 * 1024 + 10)), "large.png")}
    response = client.post("/items/new/lost", data=payload, content_type="multipart/form-data")
    assert response.status_code == 413
    with app.app_context():
        assert Item.query.count() == 0


def bytes_file():
    import io
    return io.BytesIO(b"bad data")


def test_search_category_and_location_filters(client, app):
    client.post("/register", data={"email": "student@pnu.edu.sa", "password": "strongpass123"})
    post_item(client, "lost", item_name="Library laptop")
    post_item(client, "found", item_name="Student Center keys", category="Keys", location="Student Center")
    with app.app_context():
        assert Item.query.count() == 2
    response = client.get("/listings?category=Electronics")
    assert b"Library laptop" in response.data and b"Student Center keys" not in response.data
    response = client.get("/listings?location=Student+Center")
    assert b"Student Center keys" in response.data and b"Library laptop" not in response.data
    response = client.get("/listings?category=Keys&location=Student+Center")
    assert b"Student Center keys" in response.data and b"Library laptop" not in response.data
    response = client.get("/listings?location=Sports+Center")
    assert b"No listings match the selected location" in response.data


def test_date_filter_combines_with_existing_filters(client):
    client.post("/register", data={"email": "student@pnu.edu.sa", "password": "strongpass123"})
    post_item(client, "lost", item_name="Date match", date="2026-10-01")
    post_item(client, "found", item_name="Other date", category="Keys", location="Student Center", date="2026-10-02")
    response = client.get("/listings?date=2026-10-01&type=LOST&category=Electronics&location=Library")
    assert b"Date match" in response.data and b"Other date" not in response.data
    response = client.get("/listings?date=not-a-date")
    assert b"No listings found" in response.data and b"date=not-a-date" not in response.data
    assert b"Clear" in client.get("/listings?date=2026-10-01").data


def test_contact_email_is_only_shown_to_authenticated_users(client, app):
    client.post("/register", data={"email": "poster@pnu.edu.sa", "password": "strongpass123"})
    post_item(client)
    client.post("/logout")
    assert b"poster@pnu.edu.sa" not in client.get("/listings").data
    client.post("/login", data={"email": "poster@pnu.edu.sa", "password": "strongpass123"})
    assert b"mailto:poster@pnu.edu.sa" in client.get("/listings").data
    assert b"password_hash" not in client.get("/listings").data


def test_owner_can_update_lost_and_found_status_but_others_cannot(client, app):
    client.post("/register", data={"email": "owner@pnu.edu.sa", "password": "strongpass123"})
    post_item(client, "lost", item_name="Lost item")
    post_item(client, "found", item_name="Found item")
    client.post("/logout")
    client.post("/register", data={"email": "other@pnu.edu.sa", "password": "strongpass123"})
    assert client.post("/items/1/status", data={"status": "FOUND"}).status_code == 403
    client.post("/logout")
    client.post("/login", data={"email": "owner@pnu.edu.sa", "password": "strongpass123"})
    assert client.post("/items/1/status", data={"status": "FOUND"}).status_code == 302
    assert client.post("/items/2/status", data={"status": "RETURNED"}).status_code == 302
    assert b"Status: <strong>Found</strong>" in client.get("/listings").data
    assert b"Status: <strong>Returned</strong>" in client.get("/listings").data
    assert client.post("/items/1/status", data={"status": "ACTIVE"}).status_code == 400
    with app.app_context():
        assert [item.status for item in Item.query.order_by(Item.id)] == ["FOUND", "RETURNED"]


def test_edit_listing_owner_validation_and_photo_preservation(client, app):
    client.post("/register", data={"email": "owner@pnu.edu.sa", "password": "strongpass123"})
    post_item(client)
    client.post("/logout")
    client.post("/register", data={"email": "other@pnu.edu.sa", "password": "strongpass123"})
    assert client.get("/items/1/edit").status_code == 403
    assert client.post("/items/1/edit", data={"item_name": "Changed"}).status_code == 403
    client.post("/logout")
    client.post("/login", data={"email": "owner@pnu.edu.sa", "password": "strongpass123"})
    with app.app_context():
        original_photo = Item.query.one().image_filename
    response = client.post("/items/1/edit", data={"item_name": "Updated bottle", "category": "Keys", "description": "Updated details", "location": "Library", "date": "2026-10-03"}, follow_redirects=True)
    assert b"Listing updated successfully" in response.data
    assert client.post("/items/1/edit", data={"item_name": "", "category": "Keys", "description": "x", "location": "Library", "date": "bad"}).status_code == 200
    with app.app_context():
        item = Item.query.one()
        assert (item.item_name, item.category, item.date.isoformat()) == ("Updated bottle", "Keys", "2026-10-03")
        assert item.image_filename == original_photo


def test_delete_requires_owner_and_is_post_only(client, app):
    client.post("/register", data={"email": "owner@pnu.edu.sa", "password": "strongpass123"})
    post_item(client)
    client.post("/logout")
    client.post("/register", data={"email": "other@pnu.edu.sa", "password": "strongpass123"})
    assert client.post("/items/1/delete").status_code == 403
    assert client.get("/items/1/delete").status_code == 405
    client.post("/logout")
    client.post("/login", data={"email": "owner@pnu.edu.sa", "password": "strongpass123"})
    assert client.post("/items/1/delete", follow_redirects=True).status_code == 200
    with app.app_context():
        assert Item.query.count() == 0


def test_reporting_requires_auth_reason_and_rejects_duplicate(client, app):
    client.post("/register", data={"email": "poster@pnu.edu.sa", "password": "strongpass123"})
    post_item(client)
    client.post("/logout")
    assert client.post("/items/1/report", data={"reason": "spam"}).status_code == 302
    client.post("/register", data={"email": "reporter@pnu.edu.sa", "password": "strongpass123"})
    response = client.post("/items/1/report", data={"reason": "bad"}, follow_redirects=True)
    assert b"between 5 and 1,000" in response.data
    client.post("/items/1/report", data={"reason": "This listing is inappropriate."})
    response = client.post("/items/1/report", data={"reason": "Duplicate report."}, follow_redirects=True)
    assert b"already reported" in response.data
    with app.app_context():
        assert ListingReport.query.count() == 1
        assert Item.query.count() == 1


def test_status_migration_preserves_legacy_listing_and_upload(tmp_path):
    import sqlite3
    from datetime import date
    from app import create_app

    database_path = tmp_path / "legacy.sqlite"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    image_path = upload_dir / "existing.png"
    image_path.write_bytes(b"existing upload")
    connection = sqlite3.connect(database_path)
    connection.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(254) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL, created_at DATETIME NOT NULL);
        CREATE TABLE items (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
            item_name VARCHAR(120) NOT NULL, category VARCHAR(80) NOT NULL,
            description TEXT NOT NULL, location VARCHAR(120) NOT NULL, date DATE NOT NULL,
            listing_type VARCHAR(5) NOT NULL, image_filename VARCHAR(255), created_at DATETIME NOT NULL);
        INSERT INTO users VALUES (1, 'legacy@pnu.edu.sa', 'hashed', '2026-01-01 00:00:00');
        INSERT INTO items VALUES (1, 1, 'Legacy keys', 'Keys', 'Old record', 'Library',
            '2026-01-01', 'LOST', 'existing.png', '2026-01-01 00:00:00');
    """)
    connection.commit()
    connection.close()

    migrated = create_app({"TESTING": True, "SECRET_KEY": "test-secret",
                           "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
                           "UPLOAD_FOLDER": str(upload_dir)})
    with migrated.app_context():
        item = Item.query.one()
        assert item.status == "ACTIVE"
        assert item.item_name == "Legacy keys" and item.date == date(2026, 1, 1)
        assert item.image_filename == "existing.png"
        assert User.query.one().email == "legacy@pnu.edu.sa"
        db.session.remove()
        db.engine.dispose()
    assert image_path.read_bytes() == b"existing upload"
