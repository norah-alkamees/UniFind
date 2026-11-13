import os
import secrets
from datetime import date, datetime
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, UniqueConstraint, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
CAMPUS_LOCATIONS = [
    "Main Campus", "College of Computer and Information Sciences", "College of Business",
    "Library", "Student Center", "Sports Center", "Parking Area", "Other",
]
CATEGORIES = ["Electronics", "Books & Notes", "Keys", "Bags", "Clothing", "Accessories", "ID Cards", "Other"]


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    items = db.relationship("Item", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Item(db.Model):
    __tablename__ = "items"
    __table_args__ = (CheckConstraint("listing_type IN ('LOST', 'FOUND')", name="ck_items_listing_type"),
                      CheckConstraint("status IN ('ACTIVE', 'FOUND', 'RETURNED')", name="ck_items_status"))
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    item_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(120), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    listing_type = db.Column(db.String(5), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False, default="ACTIVE", server_default="ACTIVE", index=True)
    image_filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    user = db.relationship("User", back_populates="items")
    reports = db.relationship("ListingReport", backref="item", cascade="all, delete-orphan")


class ListingReport(db.Model):
    __tablename__ = "listing_reports"
    __table_args__ = (UniqueConstraint("item_id", "reporter_id", name="uq_listing_reporter"),)
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def create_app(test_config=None):
    app = Flask(__name__)
    default_upload_dir = Path(app.instance_path) / "uploads"
    app.config.update(
        SECRET_KEY=os.environ.get("UNIFIND_SECRET_KEY") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///unifind.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", str(default_upload_dir)),
        MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    with app.app_context():
        db.create_all()
        # Additive migration for databases created before listing statuses existed.
        columns = {column["name"] for column in inspect(db.engine).get_columns("items")}
        if "status" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE items ADD COLUMN status VARCHAR(10) NOT NULL DEFAULT 'ACTIVE'"))

    @app.context_processor
    def inject_choices():
        return {"campus_locations": CAMPUS_LOCATIONS, "categories": CATEGORIES}

    @app.route("/")
    def home():
        latest = Item.query.order_by(Item.created_at.desc()).limit(6).all()
        return render_template("home.html", latest=latest)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("browse"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if not email.endswith("@pnu.edu.sa") or email.count("@") != 1 or not email.split("@")[0]:
                flash("Use a valid university email ending in @pnu.edu.sa.", "error")
            elif len(password) < 8:
                flash("Password must be at least 8 characters.", "error")
            elif User.query.filter_by(email=email).first():
                flash("An account with that email already exists.", "error")
            else:
                user = User(email=email)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                login_user(user)
                flash("Your UniFind account is ready.", "success")
                return redirect(url_for("browse"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("browse"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email).first()
            if not email.endswith("@pnu.edu.sa"):
                flash("Use your university email ending in @pnu.edu.sa.", "error")
            elif not user or not user.check_password(password):
                flash("Email or password is incorrect.", "error")
            else:
                login_user(user)
                return redirect(request.args.get("next") or url_for("browse"))
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        flash("You have been logged out.", "success")
        return redirect(url_for("home"))

    @app.route("/items/new/<listing_type>", methods=["GET", "POST"])
    @login_required
    def new_item(listing_type):
        listing_type = listing_type.upper()
        if listing_type not in {"LOST", "FOUND"}:
            abort(404)
        if request.method == "POST":
            name = request.form.get("item_name", "").strip()
            category = request.form.get("category", "").strip()
            description = request.form.get("description", "").strip()
            location = request.form.get("location", "").strip()
            item_date = request.form.get("date", "")
            upload = request.files.get("photo")
            if not all([name, category, description, location, item_date]):
                flash("Please complete all required fields.", "error")
            elif category not in CATEGORIES or location not in CAMPUS_LOCATIONS:
                flash("Choose a category and campus location from the lists.", "error")
            else:
                try:
                    parsed_date = date.fromisoformat(item_date)
                except ValueError:
                    parsed_date = None
                if not parsed_date:
                    flash("Enter a valid date.", "error")
                elif upload and upload.filename:
                    if not allowed_file(upload.filename):
                        flash("Photo must be PNG, JPG, JPEG, GIF, or WEBP.", "error")
                    else:
                        filename = secure_filename(upload.filename)
                        stored = f"{secrets.token_hex(12)}_{filename}"
                        upload.save(Path(app.config["UPLOAD_FOLDER"]) / stored)
                        item = Item(user_id=current_user.id, item_name=name, category=category,
                                    description=description, location=location, date=parsed_date,
                                    listing_type=listing_type, image_filename=stored)
                        db.session.add(item)
                        db.session.commit()
                        flash(f"{listing_type.title()} item posted successfully.", "success")
                        return redirect(url_for("browse"))
                else:
                    item = Item(user_id=current_user.id, item_name=name, category=category,
                                description=description, location=location, date=parsed_date,
                                listing_type=listing_type)
                    db.session.add(item)
                    db.session.commit()
                    flash(f"{listing_type.title()} item posted successfully.", "success")
                    return redirect(url_for("browse"))
        return render_template("new_item.html", listing_type=listing_type)

    @app.route("/listings")
    def browse():
        category = request.args.get("category", "").strip()
        location = request.args.get("location", "").strip()
        kind = request.args.get("type", "").upper().strip()
        item_date = request.args.get("date", "").strip()
        query = Item.query
        if category:
            query = query.filter(Item.category == category)
        if location:
            query = query.filter(Item.location == location)
        if kind in {"LOST", "FOUND"}:
            query = query.filter(Item.listing_type == kind)
        if item_date:
            try:
                query = query.filter(Item.date == date.fromisoformat(item_date))
            except ValueError:
                query = query.filter(text("1 = 0"))
        items = query.order_by(Item.created_at.desc()).all()
        return render_template("browse.html", items=items, selected_category=category,
                               selected_location=location, selected_type=kind, selected_date=item_date)

    @app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_item(item_id):
        item = db.get_or_404(Item, item_id)
        if item.user_id != current_user.id:
            abort(403)
        if request.method == "POST":
            name = request.form.get("item_name", "").strip()
            category = request.form.get("category", "").strip()
            description = request.form.get("description", "").strip()
            location = request.form.get("location", "").strip()
            raw_date = request.form.get("date", "").strip()
            upload = request.files.get("photo")
            try:
                parsed_date = date.fromisoformat(raw_date)
            except ValueError:
                parsed_date = None
            if not name or len(name) > 120 or not description or len(description) > 5000:
                flash("Enter an item name (up to 120 characters) and description (up to 5,000 characters).", "error")
            elif category not in CATEGORIES or location not in CAMPUS_LOCATIONS:
                flash("Choose a category and campus location from the lists.", "error")
            elif not parsed_date:
                flash("Enter a valid date.", "error")
            elif upload and upload.filename and not allowed_file(upload.filename):
                flash("Photo must be PNG, JPG, JPEG, GIF, or WEBP.", "error")
            else:
                item.item_name, item.category, item.description = name, category, description
                item.location, item.date = location, parsed_date
                if upload and upload.filename:
                    filename = secure_filename(upload.filename)
                    stored = f"{secrets.token_hex(12)}_{filename}"
                    upload.save(Path(app.config["UPLOAD_FOLDER"]) / stored)
                    item.image_filename = stored
                db.session.commit()
                flash("Listing updated successfully.", "success")
                return redirect(url_for("browse"))
        return render_template("edit_item.html", item=item)

    @app.route("/items/<int:item_id>/delete", methods=["POST"])
    @login_required
    def delete_item(item_id):
        item = db.get_or_404(Item, item_id)
        if item.user_id != current_user.id:
            abort(403)
        db.session.delete(item)
        db.session.commit()
        flash("Listing deleted.", "success")
        return redirect(url_for("browse"))

    @app.route("/items/<int:item_id>/status", methods=["POST"])
    @login_required
    def update_status(item_id):
        item = db.get_or_404(Item, item_id)
        if item.user_id != current_user.id:
            abort(403)
        expected = "FOUND" if item.listing_type == "LOST" else "RETURNED"
        if request.form.get("status") != expected:
            abort(400)
        item.status = expected
        db.session.commit()
        flash(f"Listing marked as {expected.title()}.", "success")
        return redirect(request.referrer or url_for("browse"))

    @app.route("/items/<int:item_id>/report", methods=["POST"])
    @login_required
    def report_item(item_id):
        item = db.get_or_404(Item, item_id)
        reason = request.form.get("reason", "").strip()
        if len(reason) < 5 or len(reason) > 1000:
            flash("Please provide a reason between 5 and 1,000 characters.", "error")
        elif item.user_id == current_user.id:
            flash("You cannot report your own listing.", "error")
        elif ListingReport.query.filter_by(item_id=item.id, reporter_id=current_user.id).first():
            flash("You have already reported this listing.", "error")
        else:
            db.session.add(ListingReport(item_id=item.id, reporter_id=current_user.id, reason=reason))
            try:
                db.session.commit()
                flash("Thank you. Your report was submitted for review.", "success")
            except Exception:
                db.session.rollback()
                flash("You have already reported this listing.", "error")
        return redirect(request.referrer or url_for("browse"))

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.errorhandler(413)
    def too_large(_error):
        flash("Photo is too large. The maximum upload size is 5 MB.", "error")
        return redirect(request.referrer or url_for("browse")), 413

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=os.environ.get("FLASK_DEBUG") == "1")
