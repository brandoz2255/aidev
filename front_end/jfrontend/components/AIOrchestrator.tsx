"use client"

import { useState, useEffect } from "react"

interface ModelCapabilities {
  name: string
  tasks: string[]
  speed: number // 1-10 scale
  accuracy: number // 1-10 scale
  memoryUsage: number // MB
  gpuRequired: boolean
}

interface HardwareInfo {
  gpu: boolean
  gpuMemory?: number
  cpuCores: number
  totalMemory: number
  webgl: boolean
}

export class AIOrchestrator {
  private models: ModelCapabilities[] = [
    {
      name: "mistral",
      tasks: ["general", "conversation", "reasoning"],
      speed: 8,
      accuracy: 7,
      memoryUsage: 2048,
      gpuRequired: false,
    },
    {
      name: "llama3",
      tasks: ["general", "conversation", "complex-reasoning"],
      speed: 6,
      accuracy: 9,
      memoryUsage: 4096,
      gpuRequired: true,
    },
    {
      name: "codellama",
      tasks: ["code", "programming", "debugging"],
      speed: 7,
      accuracy: 9,
      memoryUsage: 3072,
      gpuRequired: false,
    },
    {
      name: "gemma",
      tasks: ["general", "creative", "writing"],
      speed: 9,
      accuracy: 6,
      memoryUsage: 1536,
      gpuRequired: false,
    },
    {
      name: "phi3",
      tasks: ["lightweight", "mobile", "quick-response"],
      speed: 10,
      accuracy: 6,
      memoryUsage: 512,
      gpuRequired: false,
    },
    {
      name: "qwen",
      tasks: ["multilingual", "translation", "general"],
      speed: 7,
      accuracy: 8,
      memoryUsage: 2560,
      gpuRequired: false,
    },
    {
      name: "deepseek-coder",
      tasks: ["code", "programming", "technical"],
      speed: 6,
      accuracy: 10,
      memoryUsage: 3584,
      gpuRequired: true,
    },
  ]

  private hardware: HardwareInfo | null = null

  async detectHardware(): Promise<HardwareInfo> {
    const hardware: HardwareInfo = {
      gpu: false,
      cpuCores: navigator.hardwareConcurrency || 4,
      totalMemory: (navigator as any).deviceMemory ? (navigator as any).deviceMemory * 1024 : 8192,
      webgl: false,
    }

    // Detect WebGL (GPU) support
    try {
      const canvas = document.createElement("canvas")
      const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl")
      if (gl) {
        hardware.webgl = true
        hardware.gpu = true

        // Try to get GPU info
        const debugInfo = gl.getExtension("WEBGL_debug_renderer_info")
        if (debugInfo) {
          const renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL)
          console.log("GPU Renderer:", renderer)
        }
      }
    } catch (e) {
      console.log("WebGL not supported")
    }

    // Detect GPU memory (approximation)
    if (hardware.gpu) {
      hardware.gpuMemory = hardware.totalMemory > 16384 ? 8192 : 4096
    }

    this.hardware = hardware
    return hardware
  }

  selectOptimalModel(task: string, priority: "speed" | "accuracy" | "balanced" = "balanced"): string {
    if (!this.hardware) {
      return "mistral" // fallback
    }

    // Filter models that can handle the task
    const suitableModels = this.models.filter((model) =>
      model.tasks.some((t) => t.includes(task.toLowerCase()) || task.toLowerCase().includes(t)),
    )

    if (suitableModels.length === 0) {
      // No specific models for task, use general models
      const generalModels = this.models.filter((model) => model.tasks.includes("general"))
      return this.selectBestModel(generalModels, priority)
    }

    return this.selectBestModel(suitableModels, priority)
  }

  private selectBestModel(models: ModelCapabilities[], priority: "speed" | "accuracy" | "balanced"): string {
    if (!this.hardware) return models[0]?.name || "mistral"

    // Filter by hardware constraints
    const compatibleModels = models.filter((model) => {
      if (model.gpuRequired && !this.hardware!.gpu) return false
      if (model.memoryUsage > this.hardware!.totalMemory) return false
      return true
    })

    if (compatibleModels.length === 0) {
      // Fallback to lightest model
      return models.sort((a, b) => a.memoryUsage - b.memoryUsage)[0]?.name || "mistral"
    }

    // Score models based on priority
    const scoredModels = compatibleModels.map((model) => {
      let score = 0
      switch (priority) {
        case "speed":
          score = model.speed * 0.7 + model.accuracy * 0.3
          break
        case "accuracy":
          score = model.accuracy * 0.7 + model.speed * 0.3
          break
        case "balanced":
          score = (model.speed + model.accuracy) / 2
          break
      }
      return { model, score }
    })

    // Return highest scoring model
    scoredModels.sort((a, b) => b.score - a.score)
    return scoredModels[0]?.model.name || "mistral"
  }

  getModelInfo(modelName: string): ModelCapabilities | null {
    return this.models.find((m) => m.name === modelName) || null
  }

  getAllModels(): ModelCapabilities[] {
    return [...this.models]
  }
}

export function useAIOrchestrator() {
  const [orchestrator] = useState(() => new AIOrchestrator())
  const [hardware, setHardware] = useState<HardwareInfo | null>(null)
  const [isDetecting, setIsDetecting] = useState(true)

  useEffect(() => {
    const detectHardware = async () => {
      try {
        const hw = await orchestrator.detectHardware()
        setHardware(hw)
      } catch (error) {
        console.error("Hardware detection failed:", error)
      } finally {
        setIsDetecting(false)
      }
    }

    detectHardware()
  }, [orchestrator])

  return { orchestrator, hardware, isDetecting }
}
