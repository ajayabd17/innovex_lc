import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { AppHeader } from "@/components/AppHeader";

export const metadata: Metadata = {
  title: "Innovex CO-DE-GEN",
  description: "Innovex Company Detail Generator",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <Providers>
          <AppHeader />
          <div className="container-page">{children}</div>
        </Providers>
      </body>
    </html>
  );
}
