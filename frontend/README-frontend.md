# RAG System Production Frontend

This directory contains the production-ready research-grade user interface built using Next.js 14, React 18, TypeScript, Tailwind CSS, Zustand, and TanStack Query.

It features a clean, high-contrast white theme designed for clinical precision, with advanced citation rendering, quality-gate diagnostic dashboards, document ingestion management, and token expense auditing.

## Tech Stack & Architecture

- **Framework**: Next.js 14 (App Router)
- **State Management**: Zustand (chat, history, UI panel configurations)
- **API Orchestration**: TanStack Query (auto-polling health checks, query mutations, catalog invalidations)
- **Styles**: Tailwind CSS + Custom CSS vars (white-contrast aesthetics, custom focus lines)
- **Graphs**: Recharts (admin expense analysis, gate verdict charts)
- **Security**: Next.js Route Handler Proxy (`app/api/proxy/[...path]/route.ts`) to isolate backend hosts, protect headers, and sanitize payloads

## Local Setup

1. **Install Dependencies**:
   ```bash
   npm install
   ```

2. **Configure Environment Variables**:
   Copy `.env.local.example` to `.env.local`:
   ```bash
   cp .env.local.example .env.local
   ```
   Variables configured inside:
   - `BACKEND_URL`: Destination URL of the FastAPI service (defaults to `http://localhost:8000`).
   - `NEXT_PUBLIC_MAX_QUERY_LENGTH`: Ceilings for prompt inquiries (defaults to `500` characters).

3. **Start Development Server**:
   ```bash
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) to access the application.

4. **Production Build**:
   To compile Vercel-ready static pages and execute strict TypeScript type checks:
   ```bash
   npm run build
   ```

## Folder Layout

```text
frontend/
├── app/                  # Next.js App Router root
│   ├── api/proxy/        # Catch-all forwarding middleware
│   ├── chat/             # Chat workspace interface
│   ├── documents/        # Ingestion repository manager
│   ├── admin/            # Administrative diagnostics panel
│   └── layout.tsx        # HTML root loading typography
├── components/           # React component collection
│   ├── chat/             # Message timeline, pills, and sources
│   ├── documents/        # DropZone and file detail rows
│   ├── admin/            # Expense graphs and diagnostic panels
│   ├── layout/           # Sidebar and status headers
│   └── ui/               # Reusable Button, Badge, and Input primitives
├── lib/                  # Library utilities
│   ├── hooks/            # TanStack queries wrappers
│   ├── utils/            # Citation parsers and formatters
│   ├── api.ts            # Client fetching methods
│   └── store.ts          # Zustand store hooks
└── styles/               # Global reset variables
```
