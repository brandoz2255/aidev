import type React from "react"
import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "Jarvis AI - Advanced AI Assistant",
  description: "Modern AI assistant with voice, screen sharing, and chat capabilities",
  keywords: "AI, assistant, voice, screen sharing, chat, Jarvis",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-black text-white antialiased`}>{children}</body>
    </html>
  )
}
