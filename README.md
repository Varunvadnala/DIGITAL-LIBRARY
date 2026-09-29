# Digital Library for Community Centers

TYIT project · Group G-37

A small Flask project with a short book list, audio-book links, one survey, and a library comparison page. Users and survey responses are stored with the catalog in one `data.json` file. Passwords are saved as hashes.

## Run

```powershell
pip install -r requirements.txt
$env:SECRET_KEY = "use-a-long-random-value"
python -m flask --app app run --debug
```

Open `http://127.0.0.1:5000`. The first visit shows account creation; after an account exists, signed-out visits show login. The account asks for a name, study area, academic level, optional institution, email, and password.

Run the small tests with:

```powershell
python -m unittest discover -s tests -v
```

The linked books are from Project Gutenberg and OpenStax; audio links open LibriVox catalog searches. These resources are hosted externally.
