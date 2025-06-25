"use client"

import { useState, useEffect } from "react"
import ChatInterface from "@/components/ChatInterface"
import ScreenShare from "@/components/ScreenShare"
import VoiceControls from "@/components/VoiceControls"
import { motion } from "framer-motion"

export default function Home() {
  const [isLoaded, setIsLoaded] = useState(false)

  useEffect(() => {
    setIsLoaded(true)
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-br from-black via-gray-900 to-blue-900">
      <div className="container mx-auto px-4 py-8">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: isLoaded ? 1 : 0, y: isLoaded ? 0 : -20 }}
          transition={{ duration: 0.8 }}
          className="text-center mb-8"
        >
          <h1 className="text-6xl font-bold bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent mb-4">
            JARVIS AI
          </h1>
          <p className="text-gray-300 text-lg">Your Advanced AI Assistant</p>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <motion.div
            initial={{ opacity: 0, x: -50 }}
            animate={{ opacity: isLoaded ? 1 : 0, x: isLoaded ? 0 : -50 }}
            transition={{ duration: 0.8, delay: 0.2 }}
          >
            <ScreenShare />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 50 }}
            animate={{ opacity: isLoaded ? 1 : 0, x: isLoaded ? 0 : 50 }}
            transition={{ duration: 0.8, delay: 0.4 }}
          >
            <ChatInterface />
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 50 }}
          animate={{ opacity: isLoaded ? 1 : 0, y: isLoaded ? 0 : 50 }}
          transition={{ duration: 0.8, delay: 0.6 }}
          className="mt-8"
        >
          <VoiceControls />
        </motion.div>
      </div>
    </div>
  )
}
