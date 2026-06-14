# Juno Frontend

React + TypeScript + Vite web app for the Simplify pipeline. Deployed on Firebase Hosting.

## Local Development

```bash
npm install
cp .env.local.example .env.local
# Fill in .env.local values (Firebase config + backend URL)
npm run dev
# App runs at http://localhost:5173
```

## Build and Deploy

```bash
npm run build           # outputs to dist/
firebase deploy --only hosting
# Firebase gives you: https://<project>.web.app
```

## UI Flows

### Login
- Email/password only. No self-registration.
- Accounts are created manually in Firebase Console → Authentication → Users.

### Manual Upload
1. Drag & drop or click to select one or more PDF/TXT/DOCX files
2. Click "Simplify My Note"
3. Watch the 5-step pipeline progress in real time (SSE stream)
4. Result appears with sections, glossary terms, and readability scores
5. Output is automatically saved; appears in the sidebar

### Preset Dataset (Batch Mode)
1. Click "Or run a preset dataset"
2. Upload a folder with this structure:
   ```
   GroupName/
     ProcessA/
       file1.pdf
     ProcessB/
       file2.pdf
   ```
3. Each subfolder = one pipeline run, executed sequentially
4. All results saved and appear in the sidebar

### Result View
- **Summary**: plain-language overview
- **Sections**: Why You Came In, What the Doctor Found, Medications, Tests, Procedures, Follow-up, Warning Signs, Questions to Ask
- **Glossary terms**: hover any highlighted term for a plain-language definition
- **Readability score**: before/after Patient Accessibility Score

### Sidebar
- Lists all saved outputs, newest first
- Click any item to reload that result into the main view
- Three-dot menu (⋯) → Rename or Delete
- "+ New" button resets to the upload form

### Show Original
- Only available when a saved result is active
- Opens full-screen split view: left = original PDF, right = simplified output
- Both panels scroll independently

### Download Report
- Opens a new tab with a clean, print-optimized HTML report
- Click "Print / Save as PDF" in the new tab to save

## Environment Variables

Create `.env.local` for development or `.env.production` for production builds.
Use `.env.local.example` and `.env.production.example` as templates.

| Variable | Description |
|---|---|
| `VITE_FIREBASE_API_KEY` | Firebase web app API key |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase auth domain (e.g. `project.firebaseapp.com`) |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project ID |
| `VITE_FIREBASE_STORAGE_BUCKET` | Firebase storage bucket |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Firebase messaging sender ID |
| `VITE_FIREBASE_APP_ID` | Firebase app ID |
| `VITE_API_PROCESSING_URL` | Backend URL (Cloud Run URL for prod, `http://localhost:8080` for dev) |
| `VITE_DEFAULT_VERSION` | Pipeline version to use (default: `v1-2`) |
