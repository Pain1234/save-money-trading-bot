# SAVE-MONEY BOT — Hyperliquid Trading Bot Dashboard

Privates Frontend für den Hyperliquid Trading Bot unter **bot.save-money.xyz**.

## Tech Stack

- Next.js 15 (App Router)
- TypeScript
- Tailwind CSS v4
- Recharts (Performance-Chart)
- Lucide React (Icons)

## Entwicklung

```bash
npm install
npm run dev
```

Öffne [http://localhost:3000](http://localhost:3000).

## Status

Aktuell: **UI mit Mockdaten** — keine echte Hyperliquid-Integration, keine Trading-Logik, keine Wallet-Keys.

## Struktur

```
src/
├── app/              # Next.js App Router
├── components/
│   ├── dashboard/    # KPI, Chart, Tabellen, Steuerung
│   ├── layout/       # Navbar, Sidebar, Footer
│   └── ui/           # Card, Badge, KpiCard
├── lib/              # Utils & Mockdaten
└── types/            # TypeScript-Typen
```
