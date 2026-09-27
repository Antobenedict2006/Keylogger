# AI Keylogger Detection — Web Dashboard

Next.js 16 web interface for the keylogger detection system. Supports both **CSV upload** (offline analysis) and **Live Mode** (real-time streaming from Python).

---

## Quick Start

### 1. Install Dependencies
```bash
npm install
```

### 2. Run Development Server
```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Two Modes

### Upload CSV Mode (Default)
- Upload a process snapshot CSV from Task Manager, Process Explorer, or the Python CLI
- Instant ML inference (300 decision trees, 24 features)
- Works without Python running

### Live Mode
- Real-time streaming from the Python detector (`main.py`)
- Auto-refreshes every 3 seconds
- Shows ALL running processes (SAFE, SUSPICIOUS, MALICIOUS)

**To use Live Mode:**
1. Start Python detector: `cd .. && python main.py`
2. Click "Live Mode" button in the web UI
3. Data appears within 3 seconds

See [LIVE_WEB_DASHBOARD_GUIDE.md](../LIVE_WEB_DASHBOARD_GUIDE.md) for full details.

### Desktop Detection Console
The page also provides backend-backed tabs for Live Alerts, History, Statistics, Train Model, and Behavior. Start `main.py` locally to use these tabs; the Next.js API proxy forwards requests to the Python service on `127.0.0.1:8765`.

- Live alerts support terminate, quarantine, whitelist, and dismiss actions.
- History supports risk/time filters and CSV, JSON, and PDF downloads.
- Train Model exposes the backend's Start Recording action.
- Behavior shows local keyboard/mouse metrics, baseline actions, tracking settings, and privacy-aware JSON exports.
- Desktop notifications can be toggled from the web console and share state with the local detector.

These routes are designed for a local trusted machine. They do not provide the authentication, SIEM integration, or remote-access controls described as future requirements in the draft PRISM documents.

---

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
