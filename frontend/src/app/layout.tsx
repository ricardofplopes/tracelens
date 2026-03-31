import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TraceLens - Image Investigation Platform",
  description: "Investigate images using AI analysis and reverse image search",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-gray-950 text-gray-100">
        <nav className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-sm sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <a href="/" className="flex items-center space-x-2">
                <span className="text-2xl">🔍</span>
                <span className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                  TraceLens
                </span>
              </a>
              <div className="flex items-center space-x-4">
                <a href="/" className="text-gray-300 hover:text-white transition-colors text-sm">
                  New Investigation
                </a>
                <a href="/settings" className="text-gray-300 hover:text-white transition-colors text-sm">
                  Settings
                </a>
              </div>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
