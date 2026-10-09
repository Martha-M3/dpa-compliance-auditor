from app import create_app
from app.extensions import db
from app.models import User

app = create_app()

with app.app_context():
    if User.query.filter_by(username="admin").first() is None:
        admin = User(username="admin", role="Administrator")
        admin.set_password("ChangeMe123!")
        db.session.add(admin)
        print("Created Administrator: admin")
    else:
        print("'admin' already exists, skipping.")

    if User.query.filter_by(username="officer").first() is None:
        officer = User(username="officer", role="ComplianceOfficer")
        officer.set_password("ChangeMe123!")
        db.session.add(officer)
        print("Created Compliance Officer: officer")
    else:
        print("'officer' already exists, skipping.")

    db.session.commit()
    print("Done.")