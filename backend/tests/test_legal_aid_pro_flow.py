import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from fastapi.testclient import TestClient
from main import app
from routes.legal_aid import is_non_legal_query, is_substance_or_extreme_query
from models.database import SessionLocal, create_tables, User
from utils.auth import create_access_token, hash_password


def get_test_client():
    create_tables()
    return TestClient(app)


def get_db():
    db = SessionLocal()
    return db


def test_non_legal_query_detection():
    # User's exact examples:
    assert is_non_legal_query("write code for me") is True
    assert is_non_legal_query("tell me recipie") is True
    assert is_non_legal_query("tell me recipe") is True
    assert is_non_legal_query("give me recipe of biryani") is True
    assert is_non_legal_query("how to cook paneer butter masala") is True
    assert is_non_legal_query("write python code to reverse a string") is True

    # Real legal questions must NOT be flagged as non-legal:
    assert is_non_legal_query("What are the grounds for anticipatory bail under Section 438 CrPC?") is False
    assert is_non_legal_query("What is the limitation period for cheque dishonour under Section 138 NI Act?") is False
    assert is_non_legal_query("Can an FIR be quashed under Section 482 CrPC after compromise?") is False


def test_substance_detection():
    assert is_substance_or_extreme_query("i smoke weed what can police do to me") is True
    assert is_substance_or_extreme_query("what are penalties for possession of cannabis under NDPS Act?") is True
    assert is_substance_or_extreme_query("can I get bail under section 37 ndps act") is True
    assert is_substance_or_extreme_query("Can landlord evict tenant without court order?") is False


def test_auth_upgrade_to_pro(client, db_session):
    # Create a free test user
    email = "freetest@example.com"
    user = db_session.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            hashed_password=hash_password("password123"),
            full_name="Free Tier User",
            role="user"
        )
        db_session.add(user)
        db_session.commit()
    # Ensure password is correct and login
    user.hashed_password = hash_password("password123")
    user.role = "user"
    db_session.commit()

    login_res = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login_res.status_code == 200, login_res.text
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify initial role is user
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["role"] == "user"

    # Test 1: Non-legal query refusal (Free tier)
    non_legal_res = client.post("/legal-aid/ask", headers=headers, json={"question": "write code for me"})
    assert non_legal_res.status_code == 200
    assert "LexSetu is exclusively an Indian legal intelligence platform" in non_legal_res.text
    assert '"requires_upgrade":false' in non_legal_res.text.replace(" ", "")

    # Test 2: Substance query blocked on Free tier
    substance_res = client.post("/legal-aid/ask", headers=headers, json={"question": "i smoke weed what can police do to me"})
    assert substance_res.status_code == 200
    assert "Your current plan does not allow answering this question" in substance_res.text
    assert '"requires_upgrade":true' in substance_res.text.replace(" ", "")

    # Test 3: Upgrade to Pro via /auth/upgrade-pro
    upgrade_res = client.post("/auth/upgrade-pro", headers=headers)
    assert upgrade_res.status_code == 200
    data = upgrade_res.json()
    assert data["role"] == "advocate"

    # Verify role in DB
    db_session.refresh(user)
    assert user.role == "advocate"

    # Test 4: Non-legal query STILL REFUSED on Advocate Pro tier (no code/recipes on Pro!)
    pro_non_legal_res = client.post("/legal-aid/ask", headers=headers, json={"question": "tell me recipie", "upgrade_to_pro": True})
    assert pro_non_legal_res.status_code == 200
    assert "LexSetu is exclusively an Indian legal intelligence platform" in pro_non_legal_res.text
    assert '"requires_upgrade":false' in pro_non_legal_res.text.replace(" ", "")

    # Test 5: Substance inquiry now allowed on Advocate Pro tier
    # (Notice: upgrade_to_pro can also be passed inline)
    user.role = "user"
    db_session.commit()
    retry_pro_res = client.post(
        "/legal-aid/ask",
        headers=headers,
        json={"question": "i smoke weed what can police do to me", "upgrade_to_pro": True}
    )
    assert retry_pro_res.status_code == 200
    # Must NOT be blocked!
    assert "Your current plan does not allow answering this question" not in retry_pro_res.text
    assert '"is_pro":true' in retry_pro_res.text.replace(" ", "")


if __name__ == "__main__":
    print("Testing pattern detection...")
    test_non_legal_query_detection()
    test_substance_detection()
    print("Pattern tests PASSED!")

    print("Testing auth upgrade to pro & legal aid flows...")
    db = SessionLocal()
    try:
        c = TestClient(app)
        test_auth_upgrade_to_pro(c, db)
        print("All Legal Aid Pro flows PASSED successfully!")
    finally:
        db.close()

