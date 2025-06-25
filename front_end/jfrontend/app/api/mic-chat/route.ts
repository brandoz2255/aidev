import { type NextRequest, NextResponse } from "next/server"

const BACKEND_API = process.env.BACKEND_URL || "http://localhost:8000"

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()

    const response = await fetch(`${BACKEND_API}/api/mic-chat`, {
      method: "POST",
      body: formData,
    })

    if (!response.ok) {
      throw new Error(`Backend responded with ${response.status}`)
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error("Mic chat API error:", error)
    return NextResponse.json({ error: "Failed to process audio" }, { status: 500 })
  }
}
