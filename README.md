# ANATOME Setup Guide
This guide will walk you through setting up and running the project from start to finish.

---

# Prerequisites
Before you begin, make sure you have the following installed:
- **Git** (used to download the project)
  - https://git-scm.com/downloads
- **Node.js (LTS version recommended)** (includes npm)
  - https://nodejs.org/
- **Python 3.10 or newer**
  - https://www.python.org/downloads/

> **Tip:** During the Python installation on Windows, make sure to check **"Add Python to PATH"** before clicking Install.

---

# Step 1 - Download the Project
Open **Command Prompt**, **PowerShell**, or your preferred terminal.

Clone the repository (replace `<repository-url>` with the actual GitHub link):
```bash
git clone <repository-url>
```

Move into the project folder:
```bash
cd InteronIT_HackathonGroup5
```

---

# Step 2 - Set Up Environment Variables

The Generate Report feature uses Groq from the backend. Copy the template,
then set a private `GROQ_API_KEY` in `back_end/.env`:

```bash
cp back_end/.env.example back_end/.env
```

Use a freshly rotated key if an earlier key was shared in a message or exposed
elsewhere. Never put the key in frontend source, a `VITE_` variable, or GitHub.
The default report model is `openai/gpt-oss-20b`, which supports strict JSON
schema output. You can override it with `GROQ_REPORT_MODEL`.

The frontend sends report requests to `/api/reports`; Vite and Docker proxy
those requests to FastAPI. Start both services for Generate Report to work.

---

# Step 3 - Start the Application with Docker (Recommended)

If you have [Docker](https://www.docker.com/products/docker-desktop/) installed, you can start both the frontend and backend with a single command.

1. Open a terminal in the project root.
2. Run the following command:
```bash
docker compose up -d --build
```
3. Once built and running, open your browser and visit:
```
http://localhost
```
*(The backend API will also be running on `http://localhost:8000`)*

If you prefer to run the project manually without Docker, skip this step and continue to Step 4.

---

# Step 4 - Start the Backend (Manual Method)

Open a terminal in the project root and navigate to the backend folder:
```bash
cd back_end
```

Create a Python virtual environment:
```bash
python -m venv .venv
```

Activate it.

### Windows
```bash
.venv\Scripts\activate
```
> If you get an error like `cannot be loaded because running scripts is disabled on this system`, run this once in PowerShell, then try activating again:
> ```bash
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### macOS / Linux
```bash
source .venv/bin/activate
```

Install the required Python packages:
```bash
pip install -r requirements.txt
```

Start the backend:
```bash
uvicorn main:app --reload
```

You should see something similar to:
```
Uvicorn running on http://127.0.0.1:8000
```

**Leave this terminal open.**

---

# Step 5 - Start the Frontend (Manual Method)

Open **a second terminal** in the project root and navigate to the frontend folder:
```bash
cd front_end
npm install
npm run dev
```

The frontend server will start and display a URL similar to:
```
Local: http://localhost:5173/
```

**Leave this terminal open as well.**

> **Note:** Start the backend (Step 3) before the frontend. If the frontend loads before the backend is running, you may see errors or a broken-looking page until the backend is up.

> **Privacy:** Report generation sends patient age, questionnaire answers, and
> pain-region details to Groq. The patient's name stays on the ANATOME server.
> Do not use real protected health information in a public demo. Review
> privacy, retention, and vendor requirements before clinical use.

---

# Step 6 - Open the Application (Manual Method)

Open your browser and visit the address shown in the frontend terminal.

Usually this will be:
```
http://localhost:5173
```

If everything was set up correctly, the application should now be running!

---

# Troubleshooting

### `'git' is not recognized`
Git is not installed.
Download it here: https://git-scm.com/downloads

---

### `'npm' is not recognized`
Node.js is not installed.
Download the latest LTS version: https://nodejs.org/

---

### `'python' is not recognized`
Python is not installed or wasn't added to your system PATH.
Download Python: https://www.python.org/downloads/

---

### `ModuleNotFoundError`
Make sure you:
1. Activated the virtual environment.
2. Ran:
```bash
pip install -r requirements.txt
```

---

### `uvicorn` is not recognized
Run:
```bash
pip install -r requirements.txt
```
This will install Uvicorn along with the other required packages.

---

### PowerShell: "running scripts is disabled on this system"
This happens when activating the virtual environment on Windows. Run this once, then try again:
```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### Frontend loads but shows errors / blank data
Make sure the backend (Step 3) is running **before** you open the frontend in your browser. Check the backend terminal for errors.

---

# Need Help?
If you run into any issues, please include:
- The command you ran
- The full error message
- A screenshot (if possible)

This will make it much easier to diagnose the problem.

---

## ✅ Success Checklist
You should have:
- ✅ Git installed
- ✅ Node.js installed
- ✅ Python installed
- ✅ Environment variables set up (if needed)
- ✅ Backend running (`uvicorn main:app --reload`)
- ✅ Frontend running (`npm run dev`)
- ✅ Website open in your browser
