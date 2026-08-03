import { IBM_Plex_Mono, Inter } from "next/font/google";

import "./globals.css";
import { RegisterServiceWorker } from "@/components/register-service-worker";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const ibmPlexMono = IBM_Plex_Mono({
  weight: ["500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-ibm-plex-mono",
});

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${ibmPlexMono.variable}`}>
      <body className="bg-background font-sans">
        <RegisterServiceWorker />
        {children}
      </body>
    </html>
  );
}
