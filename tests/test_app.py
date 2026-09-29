import tempfile
import unittest
from pathlib import Path

import app as site


class DigitalLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_data_file = site.DATA_FILE
        site.DATA_FILE = Path(self.temporary_directory.name) / "data.json"
        site.save_data({
            "books": [{"id": 1, "title": "Sample Book", "author": "A. Writer", "category": "Literature", "description": "A sample text.", "language": "English", "level": "General", "source": "Example Library", "source_url": "https://example.org/book", "featured": True}],
            "audio_books": [], "users": [], "surveys": [],
        })
        site.app.config.update(TESTING=True, SECRET_KEY="test-key")
        self.client = site.app.test_client()

    def tearDown(self):
        site.DATA_FILE = self.original_data_file
        self.temporary_directory.cleanup()

    def csrf(self):
        with self.client.session_transaction() as stored:
            return stored["csrf_token"]

    def test_first_visit_signup_then_returning_login(self):
        first_visit = self.client.get("/")
        self.assertIn(b"Create account", first_visit.data)
        form = {"csrf_token": self.csrf(), "name": "Test Member", "study_field": "Information Technology", "education_level": "Undergraduate", "institution": "Community College", "email": "member@example.org", "password": "study-passphrase", "confirm_password": "study-passphrase"}
        self.assertEqual(self.client.post("/account?mode=register", data=form).status_code, 302)
        stored_user = site.load_data()["users"][0]
        self.assertEqual(stored_user["study_field"], "Information Technology")
        self.assertNotEqual(stored_user["password_hash"], form["password"])
        self.assertIn(b"Log in", self.client.get("/").data)
        self.client.get("/account?mode=login")
        login = self.client.post("/account?mode=login", data={"csrf_token": self.csrf(), "email": form["email"], "password": form["password"]})
        self.assertEqual(login.location, "/")
        home = self.client.get("/")
        self.assertIn(b"Community input", home.data)
        self.assertEqual(home.data.count(b"<fieldset"), 8)

    def test_library_search_and_comparison_page(self):
        result = self.client.get("/library?q=sample&type=E-Book")
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"Sample Book", result.data)
        self.assertEqual(self.client.get("/comparison").status_code, 200)

    def test_survey_saves_answers_to_single_json_file(self):
        self.client.get("/survey")
        response = self.client.post("/survey", data={
            "csrf_token": self.csrf(), "age_group": "19–25", "education": "Undergraduate",
            "resource_use": "Books", "problems": ["Expensive books"], "device": "Laptop",
            "interest": "Definitely", "feature": "Search", "feedback": "Add science books.",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(site.load_data()["surveys"][0]["feedback"], "Add science books.")


if __name__ == "__main__":
    unittest.main()
