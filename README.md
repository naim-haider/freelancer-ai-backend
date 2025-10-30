# Mactix Freelancer AI Assistant

## Overview

Mactix Freelancer AI Assistant is a powerful desktop application that streamlines the freelancing workflow by enabling users to search Freelancer projects, generate AI-powered bids, and optionally place bids automatically. Built with Python and Flask, the software is packaged as a standalone Windows executable with an easy-to-use installer—no Python installation or dependencies required.

---

## Features

- **User Authentication** - Secure login system with role-based access control
- **Project Search** - Search Freelancer projects by query, budget, and project type
- **Client Intelligence** - Fetch detailed client information including reputation, ratings, and verification status
- **AI-Powered Bids** - Generate personalized, professional bids using Google Gemini API
- **Automated Bidding** - Optionally place bids directly on Freelancer platform
- **Portable Installation** - Simple Windows installer for easy distribution and deployment
- **No Dependencies** - End users don't need Python or any additional software

---

## Project Structure

```
Freelancer_AI_Assistant/
│
├── finaltry.py              # Main Flask application
├── templates/               # HTML templates (index.html, login.html)
├── static/                  # CSS, JavaScript, and images
├── logo.ico                 # Application icon for executable
├── setup_script.iss         # Inno Setup script for installer creation
├── dist/                    # PyInstaller output folder (contains EXE)
└── README.md                # Project documentation
```

---

## Development Requirements

### Software

- Python 3.13 or higher
- PyInstaller
- Inno Setup Compiler (for creating installer)

### Python Dependencies

```bash
pip install flask requests
```

---

## Getting Started

### Step 1: Run Locally (Development)

1. Clone the repository
2. Install required dependencies:
   ```bash
   pip install flask requests
   ```
3. Run the application:
   ```bash
   python finaltry.py
   ```
4. Open your browser and navigate to: `http://127.0.0.1:5000`

#### Default Login Credentials

| Username | Password    | Role  |
| -------- | ----------- | ----- |
| admin    | admin123    | Admin |
| mactix   | mactix2024  | User  |
| user1    | password123 | User  |

---

### Step 2: Build Standalone Executable

Create a single executable file using PyInstaller:

```bash
pyinstaller --noconfirm --onefile --icon=logo.ico --name="Mactix_Freelancer_AI_Assistant" --add-data "templates;templates" --add-data "static;static" finaltry.py

```

**Command Options:**

- `--icon=logo.ico` - Sets the application icon
- `--name="..."` - Defines the executable filename
- `--add-data` - Includes necessary folders for Flask

The compiled executable will be generated in the `dist/` folder.

---

### Step 3: Create Installer (Recommended)

1. Open **Inno Setup Compiler**
2. Load `setup_script.iss`
3. Verify the executable name in the `[Files]` section matches your PyInstaller output:
   ```ini
   [Files]
   Source: "dist\Mactix_Freelancer_AI_Assistant.exe"; DestDir: "{app}"; Flags: ignoreversion
   ```
4. **(Optional)** Customize app name, installation folder, and icons in `[Setup]` and `[Icons]` sections
5. Click the **Compile** button (green ▶️)
6. The installer will be generated in the `Output` folder

---

### Step 4: Distribution

- Share **only the installer** (`Setup.exe`) with end users
- **Do not distribute** source code, `.py` files, or `.iss` files
- Users can install and run the software like any standard Windows application
- No additional software or dependencies required

---

## Configuration

### API Keys

The application requires the following API keys for full functionality:

- **GEMINI_API_KEY** - Required for AI-powered bid generation
- **PROD_TOKEN** - Required for Freelancer API integration

⚠️ **Security Warning:** Never share these API keys publicly or commit them to version control.

---

## Updating the Application

### Changing Icon or Executable Name

1. Update the PyInstaller command with new `--icon` or `--name` parameters
2. Run PyInstaller to generate the new executable in `dist/`
3. If the executable name changed, update the `setup_script.iss` file in `[Files]` and `[Icons]` sections
4. Compile the Inno Setup script to create the new installer

### Releasing New Versions

1. Update your Python code as needed
2. Rebuild the executable using PyInstaller
3. Increment the `AppVersion` in the `[Setup]` section of `setup_script.iss`
4. Recompile the installer using Inno Setup
5. Distribute only the updated installer to users

---

## Troubleshooting

| Issue                  | Solution                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------- |
| Executable not running | Ensure `--add-data` includes `templates` and `static` folders in PyInstaller command  |
| Flask 500 errors       | Check that API keys are configured correctly and network connectivity is available    |
| Installer fails        | Verify that `Source:` path in `.iss` file matches the PyInstaller executable filename |
| Icon not showing       | Confirm `.ico` file exists and the path in PyInstaller command is correct             |

---

## Recommended Distribution Files

For end users, provide:

- ✅ `Setup.exe` - Installer file
- ✅ `README.pdf` - User documentation (optional)

Do not share:

- ❌ Source code files (`.py`)
- ❌ Setup script files (`.iss`)
- ❌ Development dependencies

---

## License

[Add your license information here]

---

## Support

[Add support contact information here]

---

**Note:** This software is designed for Windows operating systems. The installer will automatically create desktop shortcuts and handle all necessary file installations.
