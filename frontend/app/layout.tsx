import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ReachPath — Prospect intelligence",
  description: "Find the legitimate path to the people who matter.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
