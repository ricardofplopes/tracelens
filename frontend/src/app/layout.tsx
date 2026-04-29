import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "../components/ThemeProvider";
import { ThemeToggle } from "../components/ThemeToggle";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "TraceLens - Image Investigation Platform",
  description: "Investigate images using AI analysis and reverse image search",
  icons: {
    icon: "/favicon.svg",
  },
};

function TraceLensLogo({ className = "w-8 h-8" }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 40 40"
      fill="none"
      className={className}
    >
      <defs>
        <linearGradient id="nav-lens" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="50%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#d946ef" />
        </linearGradient>
        <linearGradient id="nav-ring" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#818cf8" />
          <stop offset="100%" stopColor="#c084fc" />
        </linearGradient>
      </defs>
      <circle cx="17" cy="17" r="12" stroke="url(#nav-ring)" strokeWidth="2.5" fill="none" />
      <circle cx="17" cy="17" r="8.5" fill="url(#nav-lens)" opacity="0.15" />
      <line x1="17" y1="10" x2="17" y2="24" stroke="url(#nav-lens)" strokeWidth="1.2" strokeLinecap="round" opacity="0.6" />
      <line x1="10" y1="17" x2="24" y2="17" stroke="url(#nav-lens)" strokeWidth="1.2" strokeLinecap="round" opacity="0.6" />
      <circle cx="17" cy="17" r="2" fill="url(#nav-lens)" opacity="0.9" />
      <line x1="26" y1="26" x2="35" y2="35" stroke="url(#nav-lens)" strokeWidth="3.5" strokeLinecap="round" />
      <circle cx="12.5" cy="12.5" r="2.5" fill="white" opacity="0.2" />
    </svg>
  );
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="min-h-screen bg-gray-950 text-gray-100 font-sans antialiased">
        <ThemeProvider>
          <nav className="border-b border-gray-800/60 bg-gray-950/80 backdrop-blur-xl sticky top-0 z-50">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex items-center justify-between h-16">
                <a href="/" className="flex items-center gap-2.5 group">
                  <TraceLensLogo className="w-7 h-7 transition-transform group-hover:scale-110" />
                  <span className="text-lg font-semibold tracking-tight bg-gradient-to-r from-indigo-400 via-purple-400 to-fuchsia-400 bg-clip-text text-transparent">
                    TraceLens
                  </span>
                </a>
                <div className="flex items-center gap-1">
                  <a
                    href="/"
                    className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-all"
                  >
                    New Investigation
                  </a>
                  <a
                    href="/jobs"
                    className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-all"
                  >
                    History
                  </a>
                  <a
                    href="/settings"
                    className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-all"
                  >
                    Settings
                  </a>
                  <ThemeToggle />
                </div>
              </div>
            </div>
          </nav>
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
