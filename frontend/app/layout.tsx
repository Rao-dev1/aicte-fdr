import type { Metadata } from "next";
import "./globals.css";

// System fonts are used so the build does not depend on Google Fonts being reachable.
export const metadata: Metadata = {
  title: "AICTE FDR Portal",
  description: "Security deposit and FDR management for AICTE approval processes",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-slate-50 font-sans text-slate-900">{children}</body>
    </html>
  );
}
