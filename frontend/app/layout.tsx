import type { Metadata } from "next";
import "./globals.css";

// System fonts are used so the build does not depend on Google Fonts being reachable.
export const metadata: Metadata = {
  title: "AICTE Security Deposit / FDR Management Portal - Govt. of India",
  description: "AICTE Security Deposit and Fixed Deposit Receipt (FDR) lifecycle management, verification, and statutory release.",
  icons: {
    icon: "/assets/aicte_official_logo.png",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased" style={{ colorScheme: "light" }}>
      <body className="min-h-full flex flex-col bg-slate-100 text-slate-900">{children}</body>
    </html>
  );
}
