# MediBot Frontend

Next.js frontend for the MediBot RAG chatbot with role-based access control.

---

## Prerequisites

### Install Node.js via nvm

```bash
# Install nvm (Node Version Manager)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

# Reload shell configuration
source ~/.bashrc

# Install Node.js LTS version
nvm install --lts

# Verify installation
node --version   # Should show v20.x.x or higher
npm --version
```

---

## Quick Start

```bash
# Navigate to project root
cd Medibot_Hybrid_And_Sql_RAG

# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev -- -H 0.0.0.0

# Access the app
# Local: http://localhost:3000
# Network: http://<your-ip>:3000
```

---

## Configuration

### Backend API URL

The backend API URL is hardcoded in `src/lib/api.ts` as `http://localhost:8000` since frontend and backend run on the same server.

### Cross-Origin Access (for network access)

If accessing the dev server from a different machine, add your IP to `next.config.ts`:

```typescript
const nextConfig: NextConfig = {
  allowedDevOrigins: [
    "http://YOUR_IP:3000",
    "http://YOUR_IP",
    "YOUR_IP",
  ],
};
```

**Note:** Next.js doesn't support wildcards (`*`) for `allowedDevOrigins` - you must specify exact IPs. Restart the dev server after updating.

---

## Demo Accounts

| Username | Password | Role | Access |
|----------|----------|------|--------|
| dr.mehta | doctor | Doctor | general, clinical, nursing |
| nurse.priya | nurse | Nurse | general, nursing |
| billing.ravi | billing | Billing Executive | general, billing |
| tech.anand | technician | Technician | general, equipment |
| admin.sys | admin | Admin | all collections |

---

## Features

### Implemented

- [x] Login screen with 5 demo accounts (color-coded)
- [x] Chat interface with message history
- [x] Source citations (document name, section title, collection badge)
- [x] Role badge in sidebar with user avatar
- [x] Accessible collections displayed with colors
- [x] Retrieval type label (Hybrid RAG = green, SQL RAG = purple)
- [x] Markdown rendering in bot responses (bold, lists, code, tables)
- [x] Loading animation while waiting for response
- [x] Logout functionality
- [x] Session timeout (30 minutes)
- [x] Scrollable chat window (header/input fixed)
- [x] Dark blue gradient theme with #147CFA accents
- [x] Medical cross logo icon
- [x] Center-aligned sidebar content
- [x] Role-aware RBAC messaging

---

## Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx          # Root layout
│   │   ├── page.tsx            # Home (redirect)
│   │   ├── globals.css         # Global styles + markdown
│   │   ├── login/
│   │   │   └── page.tsx        # Login page
│   │   └── chat/
│   │       └── page.tsx        # Chat interface
│   └── lib/
│       └── api.ts              # API utility functions (includes hardcoded API URL)
├── next.config.ts              # Next.js config (allowedDevOrigins)
├── package.json                # Dependencies
└── README.md                   # This file
```

---

## Running Full Stack

### Terminal 1: Backend (FastAPI)

```bash
cd /path/to/Medibot_Hybrid_And_Sql_RAG
source .venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0
# Runs on http://localhost:8000
```

### Terminal 2: Frontend (Next.js)

```bash
cd /path/to/Medibot_Hybrid_And_Sql_RAG/frontend
npm run dev -- -H 0.0.0.0
# Runs on http://localhost:3000
```

---

## Useful Commands

| Command | Description |
|---------|-------------|
| `npm run dev` | Start dev server (localhost only) |
| `npm run dev -- -H 0.0.0.0` | Start dev server (all interfaces) |
| `npm run build` | Build for production |
| `npm run start` | Start production server |
| `npm run lint` | Run ESLint |
| `rm -rf .next` | Clear build cache |

---

## Troubleshooting

### "Blocked cross-origin request"
Add your IP to `allowedDevOrigins` in `next.config.ts` and restart the dev server

### Button clicks don't work
Restart dev server after config changes

### Network error on login
Make sure backend is running with `--host 0.0.0.0`

### Session expired message
Sessions timeout after 30 minutes - login again

---

## Tech Stack

- **Framework**: Next.js 16 (App Router)
- **Styling**: Tailwind CSS
- **Markdown**: react-markdown + remark-gfm
- **Language**: TypeScript
