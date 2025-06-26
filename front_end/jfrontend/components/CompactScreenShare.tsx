"use client"

import { useState, useRef, useEffect } from "react"
import { motion } from "framer-motion"
import { Monitor, MonitorOff, Eye, EyeOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"

interface CompactScreenShareProps {
  /**
   * Optional callback if you need the raw commentary + llmResponse
   */
  onAnalysis?: (caption: string, llmResponse: string) => void
}

export default function CompactScreenShare({ onAnalysis }: CompactScreenShareProps) {
  const [isSharing, setIsSharing] = useState(false)
  const [commentaryEnabled, setCommentaryEnabled] = useState(false)
  const [caption, setCaption] = useState("")          // BLIP caption
  const [llmResponse, setLlmResponse] = useState("")  // Devstral reply
  const [isAnalyzing, setIsAnalyzing] = useState(false)

  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const commentaryTimerRef = useRef<NodeJS.Timeout | null>(null)

  const startScreenShare = async () => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false,
      })
      streamRef.current = stream
      if (videoRef.current) videoRef.current.srcObject = stream
      setIsSharing(true)
      stream.getVideoTracks()[0].addEventListener("ended", stopScreenShare)
    } catch (e: any) {
      console.error("Screen-share error:", e)
      alert("Failed to start screen share: " + e.message)
    }
  }

  const stopScreenShare = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    if (videoRef.current) videoRef.current.srcObject = null
    setIsSharing(false)
    setCommentaryEnabled(false)
    setCaption("")
    setLlmResponse("")
    if (commentaryTimerRef.current) {
      clearInterval(commentaryTimerRef.current)
      commentaryTimerRef.current = null
    }
  }

  const analyzeScreen = async () => {
    if (!videoRef.current || !streamRef.current || isAnalyzing) return
    setIsAnalyzing(true)

    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const video = videoRef.current
        const canvas = document.createElement("canvas")
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        const ctx = canvas.getContext("2d")
        if (!ctx) throw new Error("No canvas context")
        ctx.drawImage(video, 0, 0)
        const imageData = canvas.toDataURL("image/jpeg", 0.8)

        // <-- changed endpoint here -->
        const res = await fetch("/api/analyze-and-respond", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image: imageData }),
        })
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()

        // parse and set both caption + LLM response
        setCaption(data.commentary || "")
        setLlmResponse(data.llm_response || "")

        // notify optional parent
        onAnalysis?.(data.commentary, data.llm_response)

        setIsAnalyzing(false)
        return
      } catch (err: any) {
        console.error(`Analyze attempt ${attempt + 1} failed:`, err)
        if (attempt === 2) {
          setCaption("Sorry, can't analyze the screen.")
          setLlmResponse("")
        }
        await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)))
      }
    }
    setIsAnalyzing(false)
  }

  const toggleCommentary = () => {
    const on = !commentaryEnabled
    setCommentaryEnabled(on)
    if (on && isSharing) {
      analyzeScreen()
      commentaryTimerRef.current = setInterval(analyzeScreen, 30_000)
    } else {
      if (commentaryTimerRef.current) {
        clearInterval(commentaryTimerRef.current)
        commentaryTimerRef.current = null
      }
      setCaption("")
      setLlmResponse("")
    }
  }

  // hotkey Ctrl/Cmd+C to trigger analysis
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "c" && isSharing) {
        e.preventDefault()
        analyzeScreen()
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [isSharing])

  // cleanup on unmount
  useEffect(() => {
    return () => {
      if (commentaryTimerRef.current) clearInterval(commentaryTimerRef.current)
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
    }
  }, [])

  return (
    <Card className="bg-gray-900/50 backdrop-blur-sm border-blue-500/30">
      <div className="p-3 border-b border-blue-500/30 flex justify-between items-center">
        <h3 className="text-lg font-semibold text-blue-300">Screen Share</h3>
        <div className="flex space-x-2">
          <Button
            size="sm"
            onClick={isSharing ? stopScreenShare : startScreenShare}
            className={`text-white ${
              isSharing ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"
            }`}
          >
            {isSharing ? <MonitorOff className="w-4 h-4" /> : <Monitor className="w-4 h-4" />}
          </Button>
          <Button
            size="sm"
            onClick={toggleCommentary}
            disabled={!isSharing}
            variant="outline"
            className={`${
              commentaryEnabled
                ? "bg-green-600 text-white hover:bg-green-700 border-green-600"
                : "bg-gray-800 text-gray-300 hover:bg-gray-700 border-gray-600"
            }`}
          >
            {commentaryEnabled ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
          </Button>
        </div>
      </div>

      <div className="p-3">
        {/* video preview */}
        <div className="relative">
          <video
            ref={videoRef}
            autoPlay
            muted
            className={`w-full rounded-lg border border-gray-600 ${
              isSharing ? "block" : "hidden"
            }`}
            style={{ maxHeight: "200px" }}
          />
          {!isSharing && (
            <div className="w-full h-32 bg-gray-800 rounded-lg border border-gray-600 flex items-center justify-center">
              <div className="text-center text-gray-400">
                <Monitor className="w-8 h-8 mb-1 opacity-50" />
                <p className="text-xs">Click to start screen capture</p>
              </div>
            </div>
          )}
        </div>

        {/* BLIP caption */}
        {caption && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-blue-900/30 border border-blue-500/50 rounded-lg p-2 mt-2"
          >
            <p className="text-xs text-blue-300 font-medium">Caption</p>
            <p className="text-xs text-gray-300 mt-1">{caption}</p>
          </motion.div>
        )}

        {/* LLM advice */}
        {llmResponse && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-green-900/30 border border-green-500/50 rounded-lg p-2 mt-2"
          >
            <p className="text-xs text-green-300 font-medium">Devstral Suggestion</p>
            <p className="text-xs text-gray-300 mt-1">{llmResponse}</p>
          </motion.div>
        )}

        {/* loading indicator */}
        {isAnalyzing && (
          <div className="flex items-center space-x-1 mt-2">
            <div className="w-1 h-1 bg-blue-400 rounded-full animate-pulse"></div>
            <span className="text-xs text-blue-400">Analyzing…</span>
          </div>
        )}
      </div>
    </Card>
  )
}
