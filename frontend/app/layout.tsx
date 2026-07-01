import React from "react";
import Providers from "@/components/Providers";
import "@/styles/globals.css";
import "@/styles/typography.css";

export const metadata = {
  title: "Clinical RAG Research Platform",
  description: "Production-grade hybrid search RAG interface with multi-gate validation controls.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body className="antialiased min-h-screen bg-white">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
