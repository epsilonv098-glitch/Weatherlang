import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Cebu Pulse",
  description: "Live weather, air quality and sea conditions across Cebu Province",
  referrer: "strict-origin-when-cross-origin", // OpenStreetMap tiles require a Referer
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <Nav />
        <main className="mx-auto max-w-5xl px-4 pb-28 pt-6 sm:pb-12">
          {children}
          <footer className="mt-10 border-t border-[var(--border)] pt-4 text-xs leading-relaxed text-[var(--muted)]">
            Weather, air quality and sea data from{" "}
            <a href="https://open-meteo.com" className="underline">Open-Meteo.com</a>; air quality based on the CAMS
            ENSEMBLE data provider. Map &copy; OpenStreetMap contributors. Values are modeled estimates for a grid
            cell and can differ from local sensors and other weather apps.
          </footer>
        </main>
      </body>
    </html>
  );
}
