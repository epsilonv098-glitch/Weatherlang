import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Cebu Pulse",
  description: "Live weather, air quality and sea conditions across Cebu Province",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <Nav />
        <main className="mx-auto max-w-5xl px-4 pb-28 pt-6 sm:pb-12">{children}</main>
      </body>
    </html>
  );
}
