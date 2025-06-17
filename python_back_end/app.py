from flask import Flask, request, jsonify, send_file
from chatbot_real import (
    chat_with_voice,
    transcribe_and_chat,
    load_tts_model,
    generate_speech
)
import os
import tempfile
import uuid

app = Flask(__name__)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message")
    history = data.get("history", [])
    selected_model = data.get("model", "mistral")

    # Optional params
    audio_prompt = data.get("audio_prompt")
    exaggeration = data.get("exaggeration", 0.5)
    temperature = data.get("temperature", 0.8)
    cfg_weight = data.get("cfg_weight", 0.5)

    # Run chat logic
    try:
        updated_history, wav = chat_with_voice(
            message, history, selected_model,
            audio_prompt, exaggeration, temperature, cfg_weight
        )

        # Save audio
        sr, samples = wav
        temp_file = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.wav")
        from soundfile import write
        write(temp_file, samples, sr)

        return jsonify({
            "history": updated_history,
            "audio_path": temp_file
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/audio/<filename>", methods=["GET"])
def serve_audio(filename):
    full_path = os.path.join(tempfile.gettempdir(), filename)
    if os.path.exists(full_path):
        return send_file(full_path, mimetype="audio/wav")
    return jsonify({"error": "File not found"}), 404


@app.route("/")
def home():
    return "🚀 Jarves API is running!"


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
