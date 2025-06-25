"use client"

import { useState, useRef } from "react"
import { motion } from "framer-motion"
import { Mic, MicOff, Volume2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"

export default function VoiceControls() {
  const [isRecording, setIsRecording] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [lastTranscription, setLastTranscription] = useState("")

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const audioRef = useRef<HTMLAudioElement>(null)

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" })
        await sendAudioToBackend(audioBlob)

        // Stop all tracks to release microphone
        stream.getTracks().forEach((track) => track.stop())
      }

      mediaRecorder.start()
      setIsRecording(true)
    } catch (error) {
      console.error("Error accessing microphone:", error)
      alert("Unable to access microphone. Please check permissions.")
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
      setIsProcessing(true)
    }
  }

  const sendAudioToBackend = async (audioBlob: Blob) => {
    // Retry logic with 3 attempts
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const formData = new FormData()
        formData.append("file", audioBlob, "mic.wav")

        const response = await fetch("/api/mic-chat", {
          method: "POST",
          body: formData,
        })

        if (!response.ok) throw new Error("Network response was not ok")

        const data = await response.json()

        // Extract the user's transcribed message
        const userMessage = data.history.find((msg: any) => msg.role === "user")
        if (userMessage) {
          setLastTranscription(userMessage.content)
        }

        if (data.audio_path) {
          setAudioUrl(data.audio_path)
          // Auto-play response
          setTimeout(() => {
            if (audioRef.current) {
              audioRef.current.play().catch(console.warn)
            }
          }, 500)
        }

        setIsProcessing(false)
        return // Success, exit retry loop
      } catch (error) {
        console.error(`Audio processing attempt ${attempt + 1} failed:`, error)
        if (attempt === 2) {
          alert("Sorry, there was an error processing your audio.")
        }
        // Wait before retry (exponential backoff)
        await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)))
      }
    }
    setIsProcessing(false)
  }

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording()
    } else {
      startRecording()
    }
  }

  const replayAudio = () => {
    if (audioRef.current) {
      audioRef.current.currentTime = 0
      audioRef.current.play()
    }
  }

  return (
    <Card className="bg-gray-900/50 backdrop-blur-sm border-blue-500/30">
      <div className="p-6">
        <h2 className="text-xl font-semibold text-blue-300 mb-4">Voice Controls</h2>

        <div className="flex flex-col items-center space-y-4">
          <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
            <Button
              onClick={toggleRecording}
              disabled={isProcessing}
              className={`w-20 h-20 rounded-full ${
                isRecording ? "bg-red-600 hover:bg-red-700 animate-pulse" : "bg-blue-600 hover:bg-blue-700"
              } text-white shadow-lg`}
            >
              {isRecording ? <MicOff className="w-8 h-8" /> : <Mic className="w-8 h-8" />}
            </Button>
          </motion.div>

          <div className="text-center">
            {isRecording && (
              <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-red-400 font-medium">
                Recording... Click to stop
              </motion.p>
            )}

            {isProcessing && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-center space-x-2 text-blue-400"
              >
                <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"></div>
                <div
                  className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"
                  style={{ animationDelay: "0.1s" }}
                ></div>
                <div
                  className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"
                  style={{ animationDelay: "0.2s" }}
                ></div>
                <span className="ml-2">Processing audio...</span>
              </motion.div>
            )}

            {!isRecording && !isProcessing && <p className="text-gray-400">Click to start voice recording</p>}
          </div>

          {lastTranscription && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-gray-800 rounded-lg p-3 max-w-md"
            >
              <p className="text-sm text-gray-300">
                <span className="text-blue-400 font-medium">You said:</span> "{lastTranscription}"
              </p>
            </motion.div>
          )}

          {audioUrl && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center space-x-3 bg-blue-900/30 rounded-lg p-3"
            >
              <Button
                onClick={replayAudio}
                variant="outline"
                size="sm"
                className="bg-gray-800 border-gray-600 text-gray-300 hover:bg-gray-700"
              >
                <Volume2 className="w-4 h-4 mr-2" />
                Replay Response
              </Button>
              <audio ref={audioRef} src={audioUrl} className="hidden" />
            </motion.div>
          )}
        </div>
      </div>
    </Card>
  )
}
